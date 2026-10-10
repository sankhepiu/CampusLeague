"""One test per input rule in the contract's "Validation" table.

Each case sends one bad value in an otherwise valid request and expects
400 validation_error naming that field, and nothing saved.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from common.testing import ApiTestCase
from common.validation import MAX_AMOUNT
from comms.models import Announcement
from events.models import Event, TicketTier
from events.tests.helpers import make_event, make_tier
from finance.models import ExpenseRequest
from finance.tests.helpers import JPG, PDF, PNG, TempMediaMixin, receipt
from shop.models import Order, Product
from shop.tests.helpers import make_product, size_of
from volunteering.models import Fundraiser, FundraiserSale, Task

User = get_user_model()


class RulesTestCase(TempMediaMixin, ApiTestCase):
    def setUp(self):
        super().setUp()
        self.now = timezone.now()
        self.today = timezone.localdate()
        self.president = self.make_role_user('president')
        self.login_as(self.president)

    def assert_rejected(self, response, field, code=None):
        body = self.assert_error(response, 400, 'validation_error', field)
        if code:
            self.assertIn((field, code), self.field_codes(body))
        # The per-field map every form can read.
        self.assertIn(field, body['fields'])
        self.assertEqual(body['fields'][field], body['message'])
        return body


class ErrorShapeTests(RulesTestCase):
    def test_fields_map_lists_every_bad_field_once(self):
        response = self.client.post('/api/events', {'title': '', 'capacity_total': 0}, format='json')
        body = self.assert_error(response, 400, 'validation_error', 'title')
        self.assertEqual(set(body), {'code', 'message', 'field', 'errors', 'fields'})
        self.assertEqual(set(body['fields']), {'title', 'venue', 'starts_at', 'ends_at', 'capacity_total'})
        self.assertEqual(set(body['fields']), {error['field'] for error in body['errors']})
        self.assertTrue(all(isinstance(message, str) and message for message in body['fields'].values()))

    def test_an_error_about_no_single_field_is_under_underscore(self):
        self.login_as(self.make_role_user('event_manager'))
        body = self.assert_error(self.client.post('/api/checkin', {}, format='json'), 400, 'validation_error')
        self.assertEqual(list(body['fields']), ['_'])


class EventRulesTests(RulesTestCase):
    def body(self, **overrides):
        starts = self.now + timedelta(days=10)
        body = {
            'title': 'Quiz Night', 'venue': 'Room 4', 'capacity_total': 50, 'status': 'on_sale',
            'starts_at': starts.isoformat(), 'ends_at': (starts + timedelta(hours=3)).isoformat(),
        }
        body.update(overrides)
        return body

    def create(self, **overrides):
        return self.client.post('/api/events', self.body(**overrides), format='json')

    def test_a_valid_event_is_accepted(self):
        self.assertEqual(self.create(description='x' * 2000, budget_amount=MAX_AMOUNT).status_code, 201)

    def test_event_must_end_after_it_starts(self):
        starts = self.now + timedelta(days=10)
        for ends in [starts, starts - timedelta(hours=1)]:
            self.assert_rejected(self.create(starts_at=starts.isoformat(), ends_at=ends.isoformat()), 'ends_at', 'ends_before_start')
        self.assertEqual(Event.objects.count(), 0)

    def test_a_new_event_cannot_start_in_the_past(self):
        starts = self.now - timedelta(hours=1)
        response = self.create(starts_at=starts.isoformat(), ends_at=(starts + timedelta(hours=3)).isoformat())
        self.assert_rejected(response, 'starts_at', 'starts_in_past')
        self.assertEqual(Event.objects.count(), 0)

    def test_an_event_cannot_be_moved_into_the_past_but_a_past_event_can_still_be_edited(self):
        future = make_event()
        response = self.client.patch(
            f'/api/events/{future.id}', {'starts_at': (self.now - timedelta(days=1)).isoformat()}, format='json',
        )
        self.assert_rejected(response, 'starts_at', 'starts_in_past')
        past = make_event(title='Old', starts_at=self.now - timedelta(days=5), ends_at=self.now - timedelta(days=5, hours=-3))
        self.assertEqual(self.client.patch(f'/api/events/{past.id}', {'status': 'closed'}, format='json').status_code, 200)
        # Re-sending the start it already has is not "moving" it.
        same = self.client.patch(f'/api/events/{past.id}', {'starts_at': past.starts_at.isoformat(), 'venue': 'Hall B'}, format='json')
        self.assertEqual(same.status_code, 200, same.content)

    def test_text_length_limits(self):
        for field, value in [('title', 'x' * 201), ('venue', 'x' * 201), ('description', 'x' * 2001), ('title', ''), ('venue', '  ')]:
            with self.subTest(field=field, length=len(value)):
                self.assert_rejected(self.create(**{field: value}), field)
        self.assertEqual(Event.objects.count(), 0)

    def test_capacity_and_budget_limits(self):
        for field, value, code in [
            ('capacity_total', 0, 'min_value'), ('capacity_total', 100_001, 'max_value'), ('capacity_total', 'many', 'invalid'),
            ('budget_amount', -1, 'min_value'), ('budget_amount', MAX_AMOUNT + 1, 'max_value'),
            ('status', 'cancelled', 'invalid_choice'),
        ]:
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.create(**{field: value}), field, code)
        self.assertEqual(Event.objects.count(), 0)

    def test_capacity_cannot_drop_below_what_tiers_hold_or_what_is_sold(self):
        event = make_event(capacity_total=100)
        tier = make_tier(event, capacity=40)
        TicketTier.objects.filter(pk=tier.pk).update(sold_count=25)
        response = self.client.patch(f'/api/events/{event.id}', {'capacity_total': 39}, format='json')
        self.assert_rejected(response, 'capacity_total', 'below_tier_capacity')
        # 40 is the least it can be: the tier's seats, 25 of them sold.
        self.assertEqual(self.client.patch(f'/api/events/{event.id}', {'capacity_total': 40}, format='json').status_code, 200)


class TierRulesTests(RulesTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event(capacity_total=100)

    def create(self, **overrides):
        body = {'name': 'General', 'public_price': 80000, 'member_price': 60000, 'capacity': 40}
        body.update(overrides)
        return self.client.post(f'/api/events/{self.event.id}/tiers', body, format='json')

    def test_prices_and_capacity(self):
        for field, value, code in [
            ('public_price', 0, 'min_value'), ('public_price', -5, 'min_value'), ('public_price', MAX_AMOUNT + 1, 'max_value'),
            ('member_price', 0, 'min_value'), ('member_price', MAX_AMOUNT + 1, 'max_value'),
            ('public_price', 12.5, 'invalid'),
            ('capacity', 0, 'min_value'), ('capacity', 101, 'exceeds_event_capacity'),
            ('name', '', 'blank'), ('name', 'x' * 101, 'max_length'),
        ]:
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.create(**{field: value}), field, code)
        self.assertEqual(TicketTier.objects.count(), 0)

    def test_sale_window_must_be_in_order_and_inside_the_event(self):
        ends = self.event.ends_at
        cases = [
            ({'sale_opens': (self.now + timedelta(days=2)).isoformat(), 'sale_closes': (self.now + timedelta(days=1)).isoformat()},
             'sale_closes', 'closes_before_opens'),
            ({'sale_closes': (ends + timedelta(minutes=1)).isoformat()}, 'sale_closes', 'outside_event'),
            ({'sale_opens': ends.isoformat()}, 'sale_opens', 'outside_event'),
            ({'sale_opens': 'whenever'}, 'sale_opens', 'invalid'),
        ]
        for overrides, field, code in cases:
            with self.subTest(overrides=overrides):
                self.assert_rejected(self.create(**overrides), field, code)
        self.assertEqual(TicketTier.objects.count(), 0)
        # Closing exactly when the event ends is allowed.
        self.assertEqual(self.create(sale_closes=ends.isoformat()).status_code, 201)

    def test_an_event_cannot_be_shortened_past_a_tiers_sale_window(self):
        make_tier(self.event, sale_closes=self.event.ends_at)
        response = self.client.patch(
            f'/api/events/{self.event.id}', {'ends_at': (self.event.ends_at - timedelta(hours=1)).isoformat()}, format='json',
        )
        self.assert_rejected(response, 'ends_at', 'before_sale_window')


class QuantityRulesTests(RulesTestCase):
    def test_ticket_quantity_is_1_to_10(self):
        tier = make_tier(make_event(), capacity=50)
        for quantity in [0, -1, 11, 'two', 1.5]:
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    f'/api/events/{tier.event_id}/tickets', {'tier': tier.id, 'quantity': quantity}, format='json',
                    HTTP_IDEMPOTENCY_KEY='quantity-key-0001',
                )
                self.assert_rejected(response, 'quantity')
        self.assertEqual(Order.objects.count(), 0)
        ok = self.client.post(
            f'/api/events/{tier.event_id}/tickets', {'tier': tier.id, 'quantity': 10}, format='json',
            HTTP_IDEMPOTENCY_KEY='quantity-key-0002',
        )
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_merch_quantity_is_1_to_10_per_item(self):
        size = size_of(make_product(stock_by_size={'M': 50}), 'M')
        for quantity in [0, 11, 'lots']:
            with self.subTest(quantity=quantity):
                response = self.client.post(
                    '/api/orders', {'items': [{'product_size': size.id, 'quantity': quantity}]}, format='json',
                    HTTP_IDEMPOTENCY_KEY='quantity-key-0003',
                )
                self.assert_rejected(response, 'items.0.quantity')
        self.assertEqual(Order.objects.count(), 0)

    def test_restock_quantity(self):
        product = make_product()
        for quantity in [0, -3, 10_001]:
            response = self.client.post(f'/api/products/{product.id}/restock', {'size': 'M', 'quantity': quantity}, format='json')
            self.assert_rejected(response, 'quantity')
        self.assert_rejected(
            self.client.post(f'/api/products/{product.id}/restock', {'size': 'XXL', 'quantity': 1}, format='json'), 'size',
        )


class ProductRulesTests(RulesTestCase):
    def create(self, **overrides):
        body = {'name': 'Scarf', 'base_price': 20000}
        body.update(overrides)
        return self.client.post('/api/products', body, format='json')

    def test_price_sale_category_and_name(self):
        make_product(name='Hoodie')
        for field, value, code in [
            ('base_price', 0, 'min_value'), ('base_price', -100, 'min_value'), ('base_price', MAX_AMOUNT + 1, 'max_value'),
            ('sale_pct', -1, 'min_value'), ('sale_pct', 91, 'max_value'), ('sale_pct', 'half', 'invalid'),
            ('category', 'weapons', 'invalid_choice'),
            ('name', '', 'blank'), ('name', 'x' * 101, 'max_length'), ('name', 'hoodie', 'unique'),
            ('description', 'x' * 2001, 'max_length'),
        ]:
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.create(**{field: value}), field, code)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(self.create(sale_pct=90).status_code, 201)

    def test_patch_is_held_to_the_same_rules(self):
        product = make_product()
        self.assert_rejected(self.client.patch(f'/api/products/{product.id}', {'sale_pct': 95}, format='json'), 'sale_pct')
        self.assert_rejected(self.client.patch(f'/api/products/{product.id}', {'base_price': 0}, format='json'), 'base_price')
        product.refresh_from_db()
        self.assertEqual((product.sale_pct, product.base_price), (0, 120000))


class ExpenseRulesTests(RulesTestCase):
    def submit(self, **overrides):
        body = {'amount': 5000, 'category': 'general', 'description': 'Printer ink', 'receipt_file': receipt()}
        body.update(overrides)
        return self.client.post('/api/expenses', body, format='multipart')

    def test_amount_is_positive_and_capped(self):
        for amount in [0, -100, MAX_AMOUNT + 1, 'ten', '12.50']:
            with self.subTest(amount=amount):
                self.assert_rejected(self.submit(amount=amount, receipt_file=receipt()), 'amount')
        self.assertEqual(ExpenseRequest.objects.count(), 0)
        self.assertEqual(self.submit(amount=MAX_AMOUNT).status_code, 201)

    def test_description_length(self):
        for description in ['', 'ab', 'x' * 501]:
            self.assert_rejected(self.submit(description=description, receipt_file=receipt()), 'description')
        self.assertEqual(ExpenseRequest.objects.count(), 0)

    def test_receipt_must_be_a_real_png_jpg_or_pdf(self):
        cases = [
            # wrong extension, although the bytes and type are a PNG's
            (receipt('receipt.gif', PNG, 'image/png'), 'unsupported_file_type'),
            (receipt('receipt.exe', PNG, 'image/png'), 'unsupported_file_type'),
            (receipt('receipt', PNG, 'image/png'), 'unsupported_file_type'),
            # right name, wrong declared content type
            (receipt('receipt.png', PNG, 'application/pdf'), 'content_type_mismatch'),
            (receipt('receipt.pdf', PDF, 'text/html'), 'content_type_mismatch'),
            (receipt('receipt.jpg', JPG, 'application/octet-stream'), 'content_type_mismatch'),
            # right name and type, but the bytes are something else
            (receipt('receipt.png', b'<html><script>alert(1)</script>', 'image/png'), 'file_content_mismatch'),
            (receipt('receipt.pdf', PNG, 'application/pdf'), 'file_content_mismatch'),
            (receipt('receipt.jpg', PDF, 'image/jpeg'), 'file_content_mismatch'),
        ]
        for upload, code in cases:
            with self.subTest(name=upload.name, type=upload.content_type, code=code):
                self.assert_rejected(self.submit(receipt_file=upload), 'receipt_file', code)
        self.assertEqual(ExpenseRequest.objects.count(), 0)

    def test_receipt_size_limit_is_5_mb(self):
        limit = 5 * 1024 * 1024
        too_big = receipt('receipt.png', PNG + b'\x00' * (limit + 1 - len(PNG)), 'image/png')
        self.assert_rejected(self.submit(receipt_file=too_big), 'receipt_file', 'file_too_large')
        exactly = receipt('receipt.png', PNG + b'\x00' * (limit - len(PNG)), 'image/png')
        self.assertEqual(self.submit(receipt_file=exactly).status_code, 201)

    def test_each_allowed_type_is_accepted(self):
        for upload in [receipt(), receipt('r.jpg', JPG, 'image/jpeg'), receipt('r.JPEG', JPG, 'image/jpeg'),
                       receipt('r.pdf', PDF, 'application/pdf')]:
            with self.subTest(name=upload.name):
                self.assertEqual(self.submit(receipt_file=upload).status_code, 201)

    def test_a_missing_receipt_is_refused(self):
        response = self.client.post('/api/expenses', {'amount': 5000, 'category': 'general', 'description': 'Ink'}, format='json')
        self.assert_rejected(response, 'receipt_file')

    def test_a_treasurer_still_cannot_approve_their_own_expense(self):
        treasurer = self.make_role_user('treasurer')
        self.login_as(treasurer)
        expense_id = self.submit().json()['id']
        self.assert_error(self.client.post(f'/api/expenses/{expense_id}/approve', {}, format='json'), 403, 'self_approval')
        self.assertEqual(ExpenseRequest.objects.get().status, 'submitted')


class VolunteeringRulesTests(RulesTestCase):
    def fundraiser(self, **overrides):
        body = {
            'title': 'Bake Sale', 'goal_amount': 100000,
            'starts_on': self.today.isoformat(), 'ends_on': (self.today + timedelta(days=7)).isoformat(),
        }
        body.update(overrides)
        return self.client.post('/api/fundraisers', body, format='json')

    def test_fundraiser_goal_dates_and_title(self):
        for field, value in [
            ('goal_amount', 0), ('goal_amount', -1), ('goal_amount', MAX_AMOUNT + 1),
            ('ends_on', (self.today - timedelta(days=1)).isoformat()), ('ends_on', '31-12-2026'),
            ('starts_on', 'soon'), ('title', ''), ('title', 'x' * 201), ('status', 'paused'),
        ]:
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.fundraiser(**{field: value}), field)
        self.assertEqual(Fundraiser.objects.count(), 0)

    def test_sale_amount_and_note(self):
        fundraiser_id = self.fundraiser().json()['id']
        for body, field in [({'amount': 0}, 'amount'), ({'amount': MAX_AMOUNT + 1}, 'amount'), ({}, 'amount'),
                            ({'amount': 500, 'note': 'x' * 201}, 'note')]:
            with self.subTest(body=body):
                self.assert_rejected(self.client.post(f'/api/fundraisers/{fundraiser_id}/sales', body, format='json'), field)
        self.assertEqual(FundraiserSale.objects.count(), 0)

    def test_task_due_date_title_and_parent(self):
        fundraiser_id = self.fundraiser().json()['id']
        base = {'fundraiser': fundraiser_id, 'title': 'Posters'}
        for overrides, field, code in [
            ({'due_date': (self.today - timedelta(days=1)).isoformat()}, 'due_date', 'in_past'),
            ({'due_date': '2026-02-30'}, 'due_date', 'invalid'),
            ({'title': ''}, 'title', 'blank'), ({'title': 'x' * 201}, 'title', 'max_length'),
            ({'description': 'x' * 2001}, 'description', 'max_length'),
            ({'fundraiser': None}, 'fundraiser', 'one_parent_required'),
        ]:
            with self.subTest(overrides=overrides):
                self.assert_rejected(self.client.post('/api/tasks', {**base, **overrides}, format='json'), field, code)
        self.assertEqual(Task.objects.count(), 0)
        today = self.client.post('/api/tasks', {**base, 'due_date': self.today.isoformat()}, format='json')
        self.assertEqual(today.status_code, 201, today.content)

    def test_an_overdue_task_can_still_be_edited_without_touching_its_date(self):
        fundraiser = Fundraiser.objects.create(title='Old', goal_amount=1000, starts_on=self.today, ends_on=self.today)
        task = Task.objects.create(fundraiser=fundraiser, title='Late', due_date=self.today - timedelta(days=3))
        self.assertEqual(self.client.patch(f'/api/tasks/{task.id}', {'title': 'Very late'}, format='json').status_code, 200)
        response = self.client.patch(f'/api/tasks/{task.id}', {'due_date': (self.today - timedelta(days=1)).isoformat()}, format='json')
        self.assert_rejected(response, 'due_date', 'in_past')

    def test_task_status_and_assignee(self):
        fundraiser = Fundraiser.objects.create(title='Sale', goal_amount=1000, starts_on=self.today, ends_on=self.today)
        task = Task.objects.create(fundraiser=fundraiser, title='Baking')
        self.assert_rejected(self.client.patch(f'/api/tasks/{task.id}/status', {'status': 'blocked'}, format='json'), 'status')
        self.assert_rejected(self.client.post(f'/api/tasks/{task.id}/assign', {'user': 999999}, format='json'), 'user')
        self.assert_rejected(
            self.client.post(f'/api/tasks/{task.id}/assign', {'user': self.president.id, 'role_note': 'x' * 201}, format='json'),
            'role_note',
        )


class AnnouncementRulesTests(RulesTestCase):
    def test_title_and_body_length(self):
        for body, field in [
            ({'title': '', 'body': 'Hello everyone'}, 'title'), ({'title': 'Hi', 'body': 'Hello everyone'}, 'title'),
            ({'title': 'x' * 201, 'body': 'Hello everyone'}, 'title'),
            ({'title': 'Notice', 'body': ''}, 'body'), ({'title': 'Notice', 'body': 'x' * 5001}, 'body'),
            ({'title': 'Notice', 'body': 'Hello everyone', 'audience': 'aliens'}, 'audience'),
        ]:
            with self.subTest(body={key: value[:12] for key, value in body.items()}):
                self.assert_rejected(self.client.post('/api/announcements', body, format='json'), field)
        self.assertEqual(Announcement.objects.count(), 0)
        ok = self.client.post('/api/announcements', {'title': 'Notice', 'body': 'x' * 5000}, format='json')
        self.assertEqual(ok.status_code, 201, ok.content)


class SignupRulesTests(RulesTestCase):
    def signup(self, **overrides):
        self.client.credentials()
        cache.clear()          # the signup throttle (10 a minute) is not what is being tested
        body = {
            'email': 'new@example.com', 'password': 'correct-horse-battery', 'name': 'New Person',
            'college_id': 'SSA-777',
        }
        body.update(overrides)
        return self.client.post('/api/auth/signup', body, format='json')

    def test_email_format(self):
        for email in ['', 'no-at-sign', 'a@', '@b.com', 'a b@c.com', 'a@b', 'x' * 250 + '@example.com']:
            with self.subTest(email=email[:20]):
                self.assert_rejected(self.signup(email=email), 'email')
        self.assertFalse(User.objects.filter(name='New Person').exists())

    def test_college_id_format(self):
        bad = ['', 'ab', 'A', 'x' * 21, 'SSA 001', 'SSA_001', '-SSA1', 'SSA1-', 'SSA/001', 'SSA.001', "SSA'--", '<b>SSA</b>']
        for college_id in bad:
            with self.subTest(college_id=college_id):
                self.assert_rejected(self.signup(college_id=college_id), 'college_id')
        self.assertFalse(User.objects.filter(name='New Person').exists())

    def test_college_ids_that_fit_the_format_are_accepted(self):
        for number, college_id in enumerate(['SSA-001', 'ssa-2026-0417', 'CS21B1042', 'A1B', 'X' * 20]):
            with self.subTest(college_id=college_id):
                response = self.signup(college_id=college_id, email=f'person{number}@example.com')
                self.assertEqual(response.status_code, 201, response.content)

    def test_name_and_phone(self):
        for field, value in [('name', ''), ('name', 'A'), ('name', 'x' * 151), ('phone', 'call me'), ('phone', '12345'),
                             ('phone', '+' + '9' * 16)]:
            with self.subTest(field=field, value=value[:16]):
                self.assert_rejected(self.signup(**{field: value}), field)
        self.assertFalse(User.objects.filter(email='new@example.com').exists())
