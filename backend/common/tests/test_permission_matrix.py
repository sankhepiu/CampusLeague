"""Every endpoint x every role -> the status it must return.

One table, read like the plan's permission table. Requests that would
change something are sent with an empty body (an allowed role then gets a
400 for the missing fields) or at an id that does not exist (an allowed role
gets a 404): either way the permission check has been passed and nothing is
written, so the rows do not depend on each other. Detailed behaviour of each
endpoint is tested in its own app.
"""
from django.urls import get_resolver
from django.utils import timezone

from common.testing import ApiTestCase
from comms.models import Announcement
from events.models import TicketPass
from events.tests.helpers import make_event, make_tier
from finance.models import ExpenseRequest
from finance.tests.helpers import TempMediaMixin
from shop.models import Coupon
from shop.payments import purchase_tickets
from shop.tests.helpers import make_product
from volunteering.models import Fundraiser, Task

ROLES = ['anonymous', 'member', 'president', 'treasurer', 'event_manager', 'volunteer_coordinator']

# Shorthand for the rows that repeat.
PUBLIC = [200] * 6
LOGGED_IN = [401] + [200] * 5
LOGGED_IN_400 = [401] + [400] * 5            # any logged-in user; empty body is refused
LOGGED_IN_404 = [401] + [404] * 5            # any logged-in user; no such object visible to them


def only(*allowed, ok=200):
    """Allowed roles get `ok`; other logged-in roles 403; anonymous 401."""
    return [401] + [ok if role in allowed else 403 for role in ROLES[1:]]


P, T, EM, VC = 'president', 'treasurer', 'event_manager', 'volunteer_coordinator'
MISSING = 999999

# (method, route as the URL conf spells it, expected status per role in ROLES order)
MATRIX = [
    # Accounts
    ('POST', 'api/auth/signup', [400] * 6),
    ('POST', 'api/auth/verify-email', [400] * 6),
    ('POST', 'api/auth/resend-code', [400] * 6),
    ('POST', 'api/auth/login', [400] * 6),
    ('POST', 'api/auth/logout', [401] + [204] * 5),
    ('GET', 'api/auth/me', LOGGED_IN),
    # Roles: president only. Invites are visible to their nominee.
    ('GET', 'api/roles', only(P)),
    ('POST', 'api/roles', only(P, ok=400)),
    ('POST', 'api/roles/<int:pk>/end', only(P, ok=404)),
    ('GET', 'api/roles/invites', LOGGED_IN),
    ('POST', 'api/roles/invites/<int:pk>/accept', LOGGED_IN_404),
    ('POST', 'api/roles/invites/<int:pk>/decline', LOGGED_IN_404),
    ('POST', 'api/roles/invites/<int:pk>/revoke', LOGGED_IN_404),
    # Members
    ('GET', 'api/members', only(P, T, EM, VC)),
    ('GET', 'api/plans', PUBLIC),
    ('POST', 'api/memberships', LOGGED_IN_400),
    ('GET', 'api/memberships/me', LOGGED_IN),
    # Events
    ('GET', 'api/events', PUBLIC),
    ('POST', 'api/events', only(P, EM, ok=400)),
    ('GET', 'api/events/<int:pk>', PUBLIC),
    ('PATCH', 'api/events/<int:pk>', only(P, EM)),
    ('POST', 'api/events/<int:pk>/tiers', only(P, EM, ok=400)),
    ('POST', 'api/events/<int:pk>/tickets', LOGGED_IN_400),
    ('GET', 'api/events/<int:pk>/attendance', only(P, T, EM)),
    ('GET', 'api/events/<int:pk>/pnl', only(P, T, EM)),
    ('GET', 'api/tickets/me', LOGGED_IN),
    # Someone else's pass: door staff may open it, others cannot see it.
    ('GET', 'api/tickets/passes/<int:pk>', [401, 404, 200, 404, 200, 200]),
    ('POST', 'api/checkin', only(P, EM, VC, ok=400)),
    # Shop
    ('GET', 'api/products', PUBLIC),
    ('POST', 'api/products', only(P, T, EM, ok=400)),
    ('GET', 'api/products/<int:pk>', PUBLIC),
    ('PATCH', 'api/products/<int:pk>', only(P, T, EM)),
    ('POST', 'api/products/<int:pk>/restock', only(P, T, EM, ok=400)),
    ('POST', 'api/orders', LOGGED_IN_400),
    ('GET', 'api/orders/me', LOGGED_IN),
    ('GET', 'api/coupons', only(P, T)),
    ('POST', 'api/coupons', only(P, T, ok=400)),
    ('POST', 'api/coupons/validate', LOGGED_IN_400),
    ('GET', 'api/coupons/<int:pk>', only(P, T)),
    ('PATCH', 'api/coupons/<int:pk>', only(P, T)),
    ('DELETE', 'api/coupons/<int:pk>', only(P, T, ok=404)),
    ('GET', 'api/payments/config', LOGGED_IN),
    ('POST', 'api/payments/razorpay/order', LOGGED_IN_400),
    ('POST', 'api/payments/razorpay/verify', LOGGED_IN_400),
    ('POST', 'api/payments/razorpay/cancel', LOGGED_IN_400),
    # Announcements
    ('GET', 'api/announcements', PUBLIC),
    ('POST', 'api/announcements', only(P, EM, VC, ok=400)),
    ('GET', 'api/announcements/<int:pk>', PUBLIC),
    ('GET', 'api/announcements/<int:pk>/deliveries', only(P, EM, VC)),
    # Finance
    ('GET', 'api/expenses', only(P, T)),
    ('POST', 'api/expenses', LOGGED_IN_400),
    ('GET', 'api/expenses/me', LOGGED_IN),
    ('POST', 'api/expenses/<int:pk>/approve', only(P, T, ok=404)),
    ('POST', 'api/expenses/<int:pk>/reject', only(P, T, ok=404)),
    ('POST', 'api/expenses/<int:pk>/mark-paid', only(P, T, ok=404)),
    ('GET', 'api/finance/summary', only(P, T)),
    ('GET', 'api/finance/ledger', only(P, T)),
    ('GET', 'api/finance/reconcile', only(P, T)),
    ('GET', 'api/finance/trace', only(P, T, ok=400)),          # no ?figure
    # Volunteering
    ('GET', 'api/fundraisers', LOGGED_IN),
    ('POST', 'api/fundraisers', only(P, VC, ok=400)),
    ('GET', 'api/fundraisers/<int:pk>', LOGGED_IN),
    ('PATCH', 'api/fundraisers/<int:pk>', only(P, VC)),
    ('POST', 'api/fundraisers/<int:pk>/sales', only(P, VC, ok=400)),
    ('POST', 'api/tasks', only(P, VC, ok=400)),
    ('PATCH', 'api/tasks/<int:pk>', only(P, VC)),
    ('POST', 'api/tasks/<int:pk>/assign', only(P, VC, ok=400)),
    # A task assigned to nobody here: coordinators only.
    ('PATCH', 'api/tasks/<int:pk>/status', only(P, VC, ok=400)),
    # Insights and audit
    ('POST', 'api/simulator', only(P, T, EM, ok=400)),
    ('GET', 'api/health', only(P)),
    ('GET', 'api/savefiles', only(P, EM)),
    ('POST', 'api/savefiles', only(P, EM, ok=400)),
    ('GET', 'api/audit', only(P)),
]

# Routes whose {id} is deliberately one that does not exist.
MISSING_ID_ROUTES = {
    'api/roles/<int:pk>/end', 'api/roles/invites/<int:pk>/accept', 'api/roles/invites/<int:pk>/decline',
    'api/roles/invites/<int:pk>/revoke', 'api/expenses/<int:pk>/approve', 'api/expenses/<int:pk>/reject',
    'api/expenses/<int:pk>/mark-paid',
}


def api_routes():
    """Every (method, route) the URL conf serves under /api/."""
    found = set()
    for group in get_resolver().url_patterns:
        for pattern in getattr(group, 'url_patterns', [group]):
            route = str(group.pattern) + (str(pattern.pattern) if pattern is not group else '')
            view = getattr(pattern.callback, 'view_class', None) or getattr(pattern.callback, 'cls', None)
            if not route.startswith('api/') or view is None:
                continue
            for method in view.http_method_names:
                if method in ('get', 'post', 'patch', 'put', 'delete') and hasattr(view, method):
                    found.add((method.upper(), route))
    return found


class PermissionMatrixTests(TempMediaMixin, ApiTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.event = make_event()
        cls.tier = make_tier(cls.event)
        cls.product = make_product()
        cls.coupon = Coupon.objects.create(code='MATRIX', kind='percent', value=10)
        cls.fundraiser = Fundraiser.objects.create(
            title='Bake Sale', goal_amount=100000, starts_on=timezone.localdate(), ends_on=timezone.localdate(),
        )
        cls.task = Task.objects.create(fundraiser=cls.fundraiser, title='Baking')

    def setUp(self):
        super().setUp()
        self.users = {role: self.make_role_user(role) for role in ROLES[1:]}
        owner = self.make_user(email='owner@example.com', college_id='SSA-OWN')
        self.announcement = Announcement.objects.create(title='Hello', body='World', author=self.users['president'])
        order = purchase_tickets(
            user=owner, tier_id=self.tier.pk, quantity=1, outcome='success', idempotency_key='matrix-key-0001',
        ).order
        self.ticket_pass = TicketPass.objects.get(order=order)
        self.ids = {
            'api/events/': self.event.pk, 'api/tickets/passes/': self.ticket_pass.pk,
            'api/products/': self.product.pk, 'api/coupons/': self.coupon.pk,
            'api/announcements/': self.announcement.pk, 'api/fundraisers/': self.fundraiser.pk,
            'api/tasks/': self.task.pk,
        }

    def url(self, method, route):
        if '<int:pk>' not in route:
            return '/' + route
        prefix = route.split('<int:pk>')[0]
        missing = route in MISSING_ID_ROUTES or (method, route) == ('DELETE', 'api/coupons/<int:pk>')
        return '/' + route.replace('<int:pk>', str(MISSING if missing else self.ids[prefix]))

    def call(self, role, method, route):
        if role == 'anonymous':
            self.client.credentials()
        else:
            self.login_as(self.users[role])
        url = self.url(method, route)
        if method == 'GET':
            return self.client.get(url)
        return getattr(self.client, method.lower())(url, {}, format='json')

    def test_the_table_covers_every_endpoint(self):
        listed = [(method, route) for method, route, _ in MATRIX]
        self.assertEqual(len(listed), len(set(listed)), 'a row is listed twice')
        self.assertEqual(set(listed), api_routes())
        for method, route, expected in MATRIX:
            self.assertEqual(len(expected), len(ROLES), (method, route))

    def test_every_endpoint_for_every_role(self):
        wrong = []
        for method, route, expected in MATRIX:
            for role, status in zip(ROLES, expected):
                response = self.call(role, method, route)
                if response.status_code != status:
                    wrong.append(f'{method} /{route} as {role}: got {response.status_code}, expected {status}')
                elif status in (401, 403):
                    code = response.json()['code']
                    if code != {401: 'not_authenticated', 403: 'permission_denied'}[status]:
                        wrong.append(f'{method} /{route} as {role}: code {code}')
        self.assertEqual(wrong, [])

    def test_nothing_was_written_by_the_matrix(self):
        """The matrix is safe to read as a pure permission table only if
        its requests change nothing."""
        before = (
            ExpenseRequest.objects.count(), Coupon.objects.count(), Task.objects.count(),
            Announcement.objects.count(), TicketPass.objects.count(), self.event.updated_at,
        )
        self.test_every_endpoint_for_every_role()
        self.event.refresh_from_db()
        self.coupon.refresh_from_db()
        after = (
            ExpenseRequest.objects.count(), Coupon.objects.count(), Task.objects.count(),
            Announcement.objects.count(), TicketPass.objects.count(), self.event.updated_at,
        )
        self.assertEqual((after[:5], self.coupon.active), (before[:5], True))

    def test_an_assignee_may_move_their_own_task_and_only_theirs(self):
        # The one object-level rule the table cannot show.
        member = self.users['member']
        self.task.assignments.create(user=member)
        other = Task.objects.create(fundraiser=self.fundraiser, title='Posters')
        self.login_as(member)
        self.assertEqual(self.client.patch(f'/api/tasks/{self.task.pk}/status', {'status': 'doing'}, format='json').status_code, 200)
        self.assert_error(
            self.client.patch(f'/api/tasks/{other.pk}/status', {'status': 'doing'}, format='json'), 403, 'permission_denied',
        )

    def test_a_role_whose_term_has_ended_is_treated_as_a_member(self):
        former = self.make_user(email='former@example.com', college_id='SSA-OLD')
        for role in [P, T, EM, VC]:
            self.give_role(former, role, start_offset=-400, end_offset=-1)
        for method, route, expected in MATRIX:
            self.login_as(former)            # a fresh token each time: one row logs out
            url = self.url(method, route)
            response = self.client.get(url) if method == 'GET' else getattr(self.client, method.lower())(url, {}, format='json')
            self.assertEqual(response.status_code, expected[ROLES.index('member')], (method, route))
