"""Demo data for the Skyline Student Association.

Plan: "One command should wipe and rebuild the demo data through the same
code paths the app uses (so ledger entries are real, not hand-inserted)."

Every membership and ticket below is bought with purchase_membership /
purchase_tickets, and every check-in goes through tickets.scan, so each one
has a genuine order, payment and balanced ledger entry behind it.

What is NOT genuine, and why:
  - Membership dates are shifted after purchase to create lapsed and
    expiring members. The ledger entry keeps today's date; the ledger is
    append-only and has no way to backdate.
  - Events, tiers, plans and role assignments are created directly; there
    is no service function for them, only API validation.
"""
import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import RoleAssignment
from audit.models import AuditLog
from events import tickets
from events.models import CheckIn, Event, Ticket, TicketTier
from finance.models import LedgerEntry, LedgerLine
from members.models import Membership, MembershipPlan
from members.services import add_months
from shop.models import Order, OrderLine, Payment
from shop.payments import purchase_membership, purchase_tickets

User = get_user_model()

# A known password for throwaway demo accounts, not a secret. The command
# refuses to run outside DEBUG so these accounts never reach a real site.
DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD', 'skyline-demo-2026')
DOMAIN = 'skyline.test'

# Wiped by reset. finance.LedgerAccount is deliberately absent: the chart of
# accounts is reference data created by a migration.
RESET_MODELS = [
    AuditLog, CheckIn, Ticket, LedgerLine, LedgerEntry, Payment, OrderLine, Order,
    TicketTier, Event, Membership, MembershipPlan, RoleAssignment, User,
]

LEADERS = [
    # (email prefix, name, role)
    ('president', 'Ananya Rao', 'president'),
    ('treasurer', 'Karthik Iyer', 'treasurer'),
    ('events', 'Meera Nair', 'event_manager'),
    ('volunteers', 'Rohan Das', 'volunteer_coordinator'),
    # Second approver: a second treasurer, so an expense raised by one
    # approver can always be approved by a different person.
    ('approver', 'Sneha Kulkarni', 'treasurer'),
]

FIRST_NAMES = [
    'Aarav', 'Diya', 'Vivaan', 'Isha', 'Aditya', 'Kavya', 'Arjun', 'Saanvi', 'Reyansh', 'Anika',
    'Krishna', 'Myra', 'Ishaan', 'Aadhya', 'Shaurya', 'Kiara', 'Atharv', 'Navya', 'Dhruv', 'Riya',
    'Kabir', 'Tara', 'Rudra', 'Zara', 'Yash', 'Nisha', 'Dev', 'Pooja', 'Neil', 'Lakshmi',
    'Om', 'Gauri', 'Samar', 'Trisha', 'Varun', 'Sana', 'Manav', 'Juhi', 'Tejas', 'Amrita',
]
SURNAMES = ['Sharma', 'Patel', 'Reddy', 'Menon', 'Singh', 'Gupta', 'Joshi', 'Pillai']

# Days of membership left for members 0..39 (negative = ended that many days
# ago). Members not listed are comfortably mid-term.
LAPSED = {36: -5, 37: -20, 38: -45, 39: -60}
EXPIRING = {32: 2, 33: 3, 34: 10, 35: 14}


def reset():
    """Empty every demo table, including the append-only ones.

    TRUNCATE is used on purpose. The ledger and audit triggers block
    row-level UPDATE and DELETE, which is what protects them in normal
    operation; TRUNCATE is a table-level command those triggers do not see.
    It is only reachable from this command, which refuses to run unless
    DEBUG is on. CASCADE also clears tables that point at these (login
    tokens, admin log). It is transactional in PostgreSQL: if the seed that
    follows fails, the old data is still there.
    """
    tables = ', '.join(connection.ops.quote_name(model._meta.db_table) for model in RESET_MODELS)
    with connection.cursor() as cursor:
        cursor.execute(f'TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE')


def _user(prefix, name, college_id, password_hash, **extra):
    user = User.objects.create_user(
        email=f'{prefix}@{DOMAIN}', name=name, college_id=college_id, **extra,
    )
    # One hash computed once and shared: hashing 46 passwords separately
    # would make the reset take many seconds.
    User.objects.filter(pk=user.pk).update(password=password_hash)
    return user


def _buy_tickets(tier, buyers, tag):
    sold = []
    for number, buyer in enumerate(buyers):
        result = purchase_tickets(
            user=buyer, tier_id=tier.pk, quantity=1, outcome='success',
            idempotency_key=f'seed-{tag}-{number:03}',
        )
        sold.extend(result.tickets)
    return sold


@transaction.atomic
def seed():
    """Build the demo data. Expects empty tables (run reset() first)."""
    today = timezone.localdate()
    now = timezone.now()
    password_hash = make_password(DEMO_PASSWORD)

    # People ---------------------------------------------------------------
    admin = _user('admin', 'Site Admin', 'SSA-ADMIN', password_hash, is_staff=True, is_superuser=True)
    leaders = {}
    for number, (prefix, name, role) in enumerate(LEADERS, start=1):
        user = _user(prefix, name, f'SSA-L{number:02}', password_hash)
        RoleAssignment.objects.create(
            user=user, role=role,
            term_start=today - timedelta(days=90), term_end=today + timedelta(days=275),
        )
        leaders[prefix] = user

    members = [
        _user(
            f'member{number + 1:02}', f'{first} {SURNAMES[number % len(SURNAMES)]}',
            f'SSA-{number + 1:03}', password_hash,
        )
        for number, first in enumerate(FIRST_NAMES)
    ]

    # Plans and memberships ------------------------------------------------
    basic = MembershipPlan.objects.create(
        name='Basic', price=50000, duration_months=12, ticket_discount_pct=0, merch_discount_pct=10,
    )
    plus = MembershipPlan.objects.create(
        name='Plus', price=90000, duration_months=12, ticket_discount_pct=0, merch_discount_pct=20,
    )
    for number, member in enumerate(members):
        plan = plus if number % 4 == 0 else basic
        membership = purchase_membership(
            user=member, plan=plan, outcome='success', idempotency_key=f'seed-membership-{number:03}',
        ).membership
        # Spread the end dates so the club has lapsed, expiring and
        # mid-term members (see the module docstring).
        days_left = LAPSED.get(number, EXPIRING.get(number, 60 + number * 7))
        end = today + timedelta(days=days_left)
        Membership.objects.filter(pk=membership.pk).update(
            start_date=add_months(end, -plan.duration_months), end_date=end,
        )

    active = [m for n, m in enumerate(members) if n not in LAPSED]
    lapsed = [m for n, m in enumerate(members) if n in LAPSED]

    # Past event: sold, attended, closed -----------------------------------
    freshers = Event.objects.create(
        title='Freshers Night', description='Welcome party for the new batch.', venue='Open Air Theatre',
        starts_at=now - timedelta(days=45), ends_at=now - timedelta(days=45) + timedelta(hours=4),
        capacity_total=60, status=Event.Status.ON_SALE, budget_amount=1200000,
    )
    freshers_tier = TicketTier.objects.create(
        event=freshers, name='General', public_price=30000, member_price=20000, capacity=60,
    )
    freshers_tickets = _buy_tickets(freshers_tier, active[:31] + lapsed, 'freshers')
    for ticket in freshers_tickets[:30]:           # 30 of 35 turned up
        tickets.scan(operator=leaders['events'], token=ticket.qr_token, event_id=freshers.pk)
    Event.objects.filter(pk=freshers.pk).update(status=Event.Status.CLOSED)

    # Spring Gala: on sale, 12 General seats left --------------------------
    gala = Event.objects.create(
        title='Spring Gala', description='The annual formal: dinner, music and awards.',
        venue='Skyline Convention Hall',
        starts_at=now + timedelta(days=30), ends_at=now + timedelta(days=30) + timedelta(hours=5),
        capacity_total=50, status=Event.Status.ON_SALE, budget_amount=3000000,
    )
    gala_general = TicketTier.objects.create(
        event=gala, name='General', public_price=80000, member_price=60000, capacity=40,
    )
    gala_vip = TicketTier.objects.create(
        event=gala, name='VIP Table', public_price=150000, member_price=120000, capacity=10,
    )
    _buy_tickets(gala_general, active[:26] + lapsed[:2], 'gala-general')
    _buy_tickets(gala_vip, active[26:29], 'gala-vip')

    # A smaller upcoming event, nothing sold yet ---------------------------
    meetup = Event.objects.create(
        title='Board Games Meetup', description='Casual evening, snacks included.',
        venue='Student Centre, Room 2',
        starts_at=now + timedelta(days=10), ends_at=now + timedelta(days=10) + timedelta(hours=3),
        capacity_total=25, status=Event.Status.ON_SALE, budget_amount=150000,
    )
    TicketTier.objects.create(event=meetup, name='Entry', public_price=10000, member_price=5000, capacity=25)

    return {
        'admin': admin, 'leaders': leaders, 'members': members,
        'lapsed': lapsed, 'expiring': [members[n] for n in EXPIRING],
    }
