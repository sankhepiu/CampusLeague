from datetime import timedelta

from django.utils import timezone

from common.testing import ApiTestCase
from events.models import Event, TicketTier
from events.tests.helpers import make_event, make_member, make_tier

EVENTS = '/api/events'


def event_body(**overrides):
    now = timezone.now()
    body = {
        'title': 'Spring Gala', 'venue': 'Main Hall', 'capacity_total': 100, 'status': 'on_sale',
        'starts_at': (now + timedelta(days=30)).isoformat(),
        'ends_at': (now + timedelta(days=30, hours=4)).isoformat(),
        'budget_amount': 2000000,
    }
    body.update(overrides)
    return body


def tier_body(**overrides):
    body = {'name': 'General', 'public_price': 80000, 'member_price': 60000, 'capacity': 60}
    body.update(overrides)
    return body


class EventReadTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event()
        self.tier = make_tier(self.event, capacity=10)

    def test_public_list_shows_events_with_tiers_and_seats_left(self):
        TicketTier.objects.filter(pk=self.tier.pk).update(sold_count=3)

        body = self.client.get(EVENTS).json()

        self.assertEqual(body['count'], 1)
        event = body['results'][0]
        self.assertEqual(event['title'], 'Spring Gala')
        self.assertNotIn('budget_amount', event)      # internal figure
        tier = event['tiers'][0]
        self.assertEqual((tier['public_price'], tier['member_price']), (80000, 60000))
        self.assertEqual(tier['seats_left'], 7)
        self.assertEqual(tier['price'], 80000)         # not logged in

    def test_price_is_the_member_price_only_for_an_active_member(self):
        user = self.make_user()
        self.login_as(user)
        url = f'{EVENTS}/{self.event.id}'
        self.assertEqual(self.client.get(url).json()['tiers'][0]['price'], 80000)

        membership = make_member(user)
        self.assertEqual(self.client.get(url).json()['tiers'][0]['price'], 60000)

        membership.end_date = timezone.localdate() - timedelta(days=1)
        membership.start_date = membership.end_date - timedelta(days=365)
        membership.save()
        self.assertEqual(self.client.get(url).json()['tiers'][0]['price'], 80000)

    def test_drafts_are_hidden_from_the_public_and_members(self):
        draft = make_event(title='Secret', status='draft')
        self.assertEqual(self.client.get(EVENTS).json()['count'], 1)
        self.assert_error(self.client.get(f'{EVENTS}/{draft.id}'), 404, 'not_found')
        self.login_as(self.make_user())
        self.assert_error(self.client.get(f'{EVENTS}/{draft.id}'), 404, 'not_found')

    def test_event_staff_see_drafts(self):
        draft = make_event(title='Secret', status='draft')
        self.login_as(self.make_role_user('event_manager'))
        self.assertEqual(self.client.get(EVENTS).json()['count'], 2)
        self.assertEqual(self.client.get(f'{EVENTS}/{draft.id}').status_code, 200)


class EventWriteTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.manager = self.make_role_user('event_manager')
        self.login_as(self.manager)

    def test_event_manager_creates_an_event_and_tiers(self):
        response = self.client.post(EVENTS, event_body(), format='json')
        self.assertEqual(response.status_code, 201, response.content)
        event = Event.objects.get()
        self.assertEqual(event.budget_amount, 2000000)

        tier = self.client.post(f'{EVENTS}/{event.id}/tiers', tier_body(), format='json')
        self.assertEqual(tier.status_code, 201, tier.content)
        self.assertEqual(tier.json()['seats_left'], 60)
        self.assertEqual(TicketTier.objects.get().sold_count, 0)

    def test_president_may_and_others_may_not_create_or_edit(self):
        event = make_event()
        for role, allowed in [
            ('president', True), ('treasurer', False), ('volunteer_coordinator', False), ('member', False),
        ]:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                responses = [
                    self.client.post(EVENTS, event_body(title=f'By {role}'), format='json'),
                    self.client.patch(f'{EVENTS}/{event.id}', {'venue': f'Hall {role}'}, format='json'),
                    self.client.post(f'{EVENTS}/{event.id}/tiers', tier_body(name=role, capacity=1), format='json'),
                ]
                for response in responses:
                    if allowed:
                        self.assertIn(response.status_code, (200, 201), response.content)
                    else:
                        self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(Event.objects.count(), 2)          # the fixture + the president's
        self.assertEqual(TicketTier.objects.count(), 1)

    def test_logged_in_user_without_a_role_and_anonymous_are_refused(self):
        self.login_as(self.make_user())
        self.assert_error(self.client.post(EVENTS, event_body(), format='json'), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.client.post(EVENTS, event_body(), format='json'), 401, 'not_authenticated')
        self.assertEqual(Event.objects.count(), 0)

    def test_invalid_events_are_refused(self):
        now = timezone.now()
        cases = [
            (event_body(title=''), 'title'),
            (event_body(capacity_total=0), 'capacity_total'),
            (event_body(capacity_total=-5), 'capacity_total'),
            (event_body(budget_amount=-1), 'budget_amount'),
            (event_body(status='cancelled'), 'status'),
            (event_body(ends_at=(now + timedelta(days=29)).isoformat()), 'ends_at'),
            (event_body(starts_at='tomorrow'), 'starts_at'),
        ]
        for body, field in cases:
            with self.subTest(field=field):
                self.assert_error(self.client.post(EVENTS, body, format='json'), 400, 'validation_error', field=field)
        self.assertEqual(Event.objects.count(), 0)

    def test_patch_changes_status_and_put_is_not_allowed(self):
        event = make_event(status='draft')
        response = self.client.patch(f'{EVENTS}/{event.id}', {'status': 'on_sale'}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        event.refresh_from_db()
        self.assertEqual(event.status, 'on_sale')
        self.assert_error(self.client.put(f'{EVENTS}/{event.id}', event_body(), format='json'), 405, 'method_not_allowed')

    def test_patch_cannot_make_the_event_end_before_it_starts(self):
        event = make_event()
        response = self.client.patch(
            f'{EVENTS}/{event.id}', {'ends_at': (event.starts_at - timedelta(hours=1)).isoformat()}, format='json',
        )
        self.assert_error(response, 400, 'validation_error', field='ends_at')

    # Team decision: tier capacities may not add up to more than capacity_total.

    def test_tiers_cannot_exceed_event_capacity(self):
        event = make_event(capacity_total=100)
        url = f'{EVENTS}/{event.id}/tiers'
        self.assertEqual(self.client.post(url, tier_body(name='Member', capacity=60), format='json').status_code, 201)

        over = self.client.post(url, tier_body(name='Public', capacity=41), format='json')
        body = self.assert_error(over, 400, 'validation_error', field='capacity')
        self.assertEqual(self.field_codes(body), {('capacity', 'exceeds_event_capacity')})

        exact = self.client.post(url, tier_body(name='Public', capacity=40), format='json')
        self.assertEqual(exact.status_code, 201, exact.content)
        self.assertEqual(TicketTier.objects.filter(event=event).count(), 2)

    def test_event_capacity_cannot_be_lowered_below_its_tiers(self):
        event = make_event(capacity_total=100)
        make_tier(event, capacity=60)
        response = self.client.patch(f'{EVENTS}/{event.id}', {'capacity_total': 59}, format='json')
        self.assert_error(response, 400, 'validation_error', field='capacity_total')
        self.assertEqual(self.client.patch(f'{EVENTS}/{event.id}', {'capacity_total': 60}, format='json').status_code, 200)

    def test_invalid_tiers_are_refused(self):
        event = make_event()
        make_tier(event, name='General', capacity=1)
        now = timezone.now()
        cases = [
            (tier_body(name='General'), 'name'),
            (tier_body(name='A', public_price=0), 'public_price'),
            (tier_body(name='B', member_price=-1), 'member_price'),
            (tier_body(name='C', capacity=0), 'capacity'),
            (tier_body(name='D', sale_opens=now.isoformat(), sale_closes=(now - timedelta(days=1)).isoformat()), 'sale_closes'),
        ]
        for body, field in cases:
            with self.subTest(field=field):
                response = self.client.post(f'{EVENTS}/{event.id}/tiers', body, format='json')
                self.assert_error(response, 400, 'validation_error', field=field)
        self.assertEqual(TicketTier.objects.count(), 1)

    def test_sold_count_cannot_be_set_through_the_api(self):
        event = make_event()
        self.client.post(f'{EVENTS}/{event.id}/tiers', tier_body(sold_count=50), format='json')
        self.assertEqual(TicketTier.objects.get().sold_count, 0)

    def test_tier_for_unknown_event_is_404(self):
        self.assert_error(self.client.post(f'{EVENTS}/999999/tiers', tier_body(), format='json'), 404, 'not_found')
