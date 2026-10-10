from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditLog
from common.admin import rupees
from events.models import CheckIn, Event, Ticket, TicketTier
from events.tests.helpers import make_event, make_tier
from events.tickets import scan
from finance.models import ExpenseRequest, LedgerAccount, LedgerEntry
from insights.models import SaveFile
from shop.models import Order, ProductSize
from shop.payments import purchase_merch, purchase_tickets
from shop.tests.helpers import make_product, size_of

User = get_user_model()

READ_ONLY_MODELS = [
    LedgerAccount, LedgerEntry, ExpenseRequest, Event, TicketTier, Ticket, CheckIn,
    Order, ProductSize, SaveFile, AuditLog,
]


class ReadOnlyAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            email='admin@example.com', password='correct-horse-battery', name='Admin', college_id='A1',
        )
        buyer = User.objects.create_user(email='buyer@example.com', name='Buyer', college_id='B1')
        event = make_event()
        cls.ticket = purchase_tickets(
            user=buyer, tier_id=make_tier(event).id, quantity=1, outcome='success', idempotency_key='admin-test-key-1',
        ).tickets[0]
        scan(operator=cls.admin_user, token=cls.ticket.qr_token)
        hoodie = make_product('Hoodie', 120000, {'M': 5})
        purchase_merch(user=buyer, items={size_of(hoodie, 'M').pk: 2}, outcome='success', idempotency_key='admin-test-key-2')
        ExpenseRequest.objects.create(
            requester=buyer, amount=150000, category='event', event=event, description='Catering', receipt_file='receipts/x.png',
        )
        SaveFile.objects.create(event=event, vendors='Beatbox Audio')

    def setUp(self):
        self.client.force_login(self.admin_user)

    def url(self, model, page, *args):
        return reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_{page}', args=args)

    def test_every_listed_model_is_registered(self):
        for model in READ_ONLY_MODELS:
            self.assertIn(model, admin.site._registry, model.__name__)

    def test_even_a_superuser_cannot_add_change_or_delete(self):
        request = self.client.get('/admin/').wsgi_request
        for model in READ_ONLY_MODELS:
            with self.subTest(model=model.__name__):
                model_admin = admin.site._registry[model]
                instance = model.objects.first()
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request, instance))
                self.assertFalse(model_admin.has_delete_permission(request, instance))
                self.assertTrue(model_admin.has_view_permission(request, instance))

    def test_list_and_detail_pages_open(self):
        for model in READ_ONLY_MODELS:
            with self.subTest(model=model.__name__):
                self.assertEqual(self.client.get(self.url(model, 'changelist')).status_code, 200)
                instance = model.objects.first()
                self.assertIsNotNone(instance, 'fixture should include one of each')
                self.assertEqual(self.client.get(self.url(model, 'change', instance.pk)).status_code, 200)

    def test_add_delete_and_save_are_refused_over_http(self):
        for model in READ_ONLY_MODELS:
            with self.subTest(model=model.__name__):
                instance = model.objects.first()
                self.assertEqual(self.client.get(self.url(model, 'add')).status_code, 403)
                self.assertEqual(self.client.post(self.url(model, 'add'), {}).status_code, 403)
                self.assertEqual(self.client.post(self.url(model, 'delete', instance.pk), {'post': 'yes'}).status_code, 403)
                self.assertEqual(self.client.post(self.url(model, 'change', instance.pk), {'description': 'edited'}).status_code, 403)
                self.assertTrue(model.objects.filter(pk=instance.pk).exists())

    def test_bulk_delete_action_is_not_offered(self):
        for model in READ_ONLY_MODELS:
            with self.subTest(model=model.__name__):
                response = self.client.post(self.url(model, 'changelist'), {
                    'action': 'delete_selected', '_selected_action': [model.objects.first().pk], 'post': 'yes',
                })
                self.assertNotEqual(response.status_code, 500)
                self.assertTrue(model.objects.exists())

    def test_amounts_are_shown_in_rupees(self):
        self.assertEqual([rupees(120000), rupees(5), rupees(0), rupees(None), rupees(12345678)],
                         ['Rs 1,200.00', 'Rs 0.05', 'Rs 0.00', '', 'Rs 123,456.78'])
        pages = {
            self.url(Order, 'changelist'): 'Rs 2,400.00',                # 2 hoodies
            self.url(LedgerEntry, 'changelist'): 'Rs 800.00',            # the ticket sale
            self.url(Ticket, 'changelist'): 'Rs 800.00',
            self.url(TicketTier, 'changelist'): 'Rs 600.00',             # member price
            self.url(ExpenseRequest, 'changelist'): 'Rs 1,500.00',
            self.url(ProductSize, 'changelist'): 'Rs 1,200.00',
        }
        for url, expected in pages.items():
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), expected)

    def test_entry_and_order_pages_show_their_lines_in_rupees(self):
        entry = LedgerEntry.objects.get(kind='ticket_sale')
        page = self.client.get(self.url(LedgerEntry, 'change', entry.pk))
        self.assertContains(page, 'Rs 800.00')
        self.assertContains(page, 'Ticket revenue')
        self.assertContains(page, 'Cash and bank')

        order = Order.objects.get(lines__kind='merch')
        page = self.client.get(self.url(Order, 'change', order.pk))
        self.assertContains(page, 'Rs 1,200.00')         # unit price
        self.assertContains(page, 'Rs 2,400.00')         # paid

    def test_ticket_page_does_not_show_the_qr_token(self):
        page = self.client.get(self.url(Ticket, 'change', self.ticket.pk))
        self.assertContains(page, self.ticket.code)
        self.assertNotContains(page, self.ticket.qr_token)

    def test_admin_is_closed_to_non_staff(self):
        self.client.logout()
        buyer = User.objects.get(email='buyer@example.com')
        self.client.force_login(buyer)
        response = self.client.get(self.url(LedgerEntry, 'changelist'))
        self.assertEqual(response.status_code, 302)       # sent to the admin login page
        self.assertIn('/admin/login/', response['Location'])
