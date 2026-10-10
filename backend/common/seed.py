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
  - Events, tiers, plans, products and role assignments are created
    directly; there is no service function for them, only API validation.
  - Expense requests are created directly with a generated placeholder
    receipt image (the API's only extra step is validating the upload);
    every approval, rejection and payout goes through finance.expenses.
  - The two past announcements go through the real publish and send code,
    but with a sender that discards the message, so resetting does not
    print 90 emails. Their deliveries read "sent" although nothing left
    the machine, and their dates are moved into the past afterwards.
"""
import os
import struct
import zlib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import RoleAssignment
from audit.models import AuditLog
from comms import services as comms
from comms.models import Announcement, AnnouncementDelivery
from events import tickets
from events.models import CheckIn, Event, Ticket, TicketTier
from finance import expenses
from finance.models import Approval, ExpenseRequest, LedgerEntry, LedgerLine
from members.models import Membership, MembershipPlan
from members.services import add_months
from shop import stock
from shop.models import Order, OrderLine, Payment, Product, ProductSize, StockMovement
from shop.payments import purchase_membership, purchase_merch, purchase_tickets
from volunteering.models import Fundraiser, FundraiserSale, Task, TaskAssignment
from volunteering.services import record_sale

User = get_user_model()

# A known password for throwaway demo accounts, not a secret. The command
# refuses to run outside DEBUG so these accounts never reach a real site.
DEMO_PASSWORD = os.environ.get('DEMO_PASSWORD', 'skyline-demo-2026')
DOMAIN = 'skyline.test'

# Wiped by reset. finance.LedgerAccount is deliberately absent: the chart of
# accounts is reference data created by a migration.
RESET_MODELS = [
    AuditLog, AnnouncementDelivery, Announcement, Approval, ExpenseRequest, FundraiserSale,
    TaskAssignment, Task, Fundraiser, CheckIn, Ticket, LedgerLine, LedgerEntry,
    StockMovement, Payment, OrderLine, Order, ProductSize, Product,
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


def remove_orphan_receipts():
    """Delete receipt files no expense request points at any more.

    Files are not covered by the database transaction, so this runs only
    after reset and seed have committed: a failed seed leaves both the old
    rows and their files in place.
    """
    folder = os.path.join(settings.MEDIA_ROOT, 'receipts')
    if not os.path.isdir(folder):
        return 0
    in_use = {os.path.basename(name) for name in ExpenseRequest.objects.values_list('receipt_file', flat=True)}
    stale = [name for name in os.listdir(folder) if name not in in_use]
    for name in stale:
        os.remove(os.path.join(folder, name))
    return len(stale)


def _placeholder_receipt(width=160, height=220):
    """A small, valid grey PNG to stand in for a photographed receipt."""
    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))

    row = b'\x00' + b'\xe6' * width                    # filter byte + one grey pixel per column
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(row * height))
        + chunk(b'IEND', b'')
    )


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

    # Merchandise ----------------------------------------------------------
    # (name, price, description, {size: (restocked, sold)})
    catalogue = [
        ('Skyline Hoodie', 120000, 'Heavyweight fleece with the club crest.',
         {'S': (10, 2), 'M': (8, 3), 'L': (8, 2), 'XL': (3, 2)}),       # XL: 1 left
        ('Skyline T-Shirt', 40000, 'Cotton tee, club colours.',
         {'S': (15, 0), 'M': (20, 4), 'L': (15, 2), 'XL': (10, 0)}),
    ]
    shoppers = iter(active * 2)
    for name, price, description, sizes in catalogue:
        product = Product.objects.create(name=name, base_price=price, description=description)
        for size, (restocked, sold) in sizes.items():
            row = ProductSize.objects.create(product=product, size=size)
            stock.restock(product_size=row, quantity=restocked, actor=leaders['treasurer'])
            for number in range(sold):
                purchase_merch(
                    user=next(shoppers), items={row.pk: 1}, outcome='success',
                    idempotency_key=f'seed-merch-{row.pk:03}-{number:02}',
                )

    # Announcements --------------------------------------------------------
    past_posts = [
        (20, leaders['president'], 'Welcome to the new term',
         'Memberships for the year are open. Join from the Plans page to get member prices.'),
        (6, leaders['events'], 'Spring Gala tickets are live',
         'General and VIP tickets are on sale now. Members pay less, and seats are limited.'),
    ]
    for days_ago, author, title, body in past_posts:
        announcement = comms.publish(author=author, title=title, body=body)
        comms.send_pending(announcement, send=lambda delivery: None)
        Announcement.objects.filter(pk=announcement.pk).update(published_at=now - timedelta(days=days_ago))

    # Bake sale fundraiser: tasks with owners, goal bar about half full ----
    bake_sale = Fundraiser.objects.create(
        title='Bake Sale', goal_amount=1500000,
        starts_on=today - timedelta(days=6), ends_on=today + timedelta(days=8),
    )
    for title, status, owners in [
        ('Baking', 'done', [(members[1], 'Brownies'), (members[2], 'Cookies')]),
        ('Supplies', 'doing', [(members[3], 'Boxes and napkins')]),
        ('Table', 'todo', [(members[5], 'Saturday shift')]),
        ('Posters', 'todo', []),                                    # nobody yet
    ]:
        task = Task.objects.create(fundraiser=bake_sale, title=title, status=status, due_date=today + timedelta(days=3))
        for owner, note in owners:
            TaskAssignment.objects.create(task=task, user=owner, role_note=note)
    for amount, note in [(250000, 'Day 1 stall'), (310000, 'Day 2 stall'), (180000, 'Pre-orders')]:
        record_sale(fundraiser=bake_sale, amount=amount, recorded_by=leaders['volunteers'], note=note)

    # Expenses: paid, approved, rejected, and one waiting for the live demo
    treasurer, second = leaders['treasurer'], leaders['approver']
    receipt = _placeholder_receipt()

    def expense(requester, amount, description, category='event', event=None, fundraiser=None):
        request = ExpenseRequest(
            requester=requester, amount=amount, description=description,
            category=category, event=event, fundraiser=fundraiser,
        )
        request.receipt_file.save('receipt.png', ContentFile(receipt), save=True)
        return request

    for requester, amount, description, event, outcome in [
        (members[6], 250000, 'Sound system hire', freshers, 'paid'),
        (members[7], 80000, 'Decorations', freshers, 'paid'),
        (members[8], 120000, 'Snacks and water', freshers, 'approved'),
        (leaders['events'], 500000, 'Venue deposit', gala, 'paid'),
    ]:
        request = expense(requester, amount, description, event=event)
        expenses.approve(request.pk, treasurer, 'Receipt matches')
        if outcome == 'paid':
            expenses.mark_paid(request.pk, second)
    expenses.approve(expense(members[1], 15000, 'Baking ingredients', 'fundraiser', fundraiser=bake_sale).pk, second)
    expenses.reject(expense(members[9], 4500, 'Printer ink', 'general').pk, treasurer, 'Not agreed beforehand')
    # Left as submitted: approve it live as the treasurer.
    expense(members[4], 35000, 'Stage flowers', event=gala)

    return {
        'admin': admin, 'leaders': leaders, 'members': members,
        'lapsed': lapsed, 'expiring': [members[n] for n in EXPIRING],
    }
