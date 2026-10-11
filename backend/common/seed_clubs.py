"""Demo data for the clubs that are not Skyline.

Each of these clubs lives in its own database schema (see common/clubs.py),
so this runs inside `use_club(slug)` and uses exactly the same services as
the Skyline seed: every membership, ticket and merch order is a real
purchase with a payment and a balanced ledger entry, and every expense
decision goes through finance.expenses.

Smaller than Skyline's on purpose: enough for each screen to have something
on it. Skyline's own seed (common/seed.py) is not touched.
"""
import os
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from accounts.models import RoleAssignment
from common import pixel_art, seed_events
from common.seed import DEMO_PASSWORD, _placeholder_receipt, _user
from events import tickets
from events.models import Event, TicketTier
from finance import expenses
from finance.models import ExpenseRequest
from members.models import MembershipPlan
from shop import stock
from shop.models import Product, ProductSize
from shop.payments import purchase_membership, purchase_merch, purchase_tickets
from volunteering.models import Fundraiser, Task, TaskAssignment
from volunteering.services import record_sale

LEADERS = [
    # (email prefix, role). The second treasurer is the "approver", so an
    # expense raised by one approver can be approved by the other.
    ('president', 'president'), ('treasurer', 'treasurer'), ('approver', 'treasurer'),
    ('events', 'event_manager'), ('volunteers', 'volunteer_coordinator'),
]
MEMBER_COUNT = 15

CLUB_DATA = {
    'robotics': {
        'domain': 'robotics.test',
        'id_prefix': 'PRC',
        'leaders': ['Ishita Bose', 'Nikhil Rao', 'Farah Khan', 'Tanmay Joshi', 'Ritika Sen'],
        'members': ['Aryan', 'Bhavna', 'Chirag', 'Deepa', 'Eshan', 'Fatima', 'Gautam', 'Harini',
                    'Imran', 'Jaya', 'Kunal', 'Leela', 'Mohit', 'Nandini', 'Omkar'],
        # Skyline accounts that also join this club: the same email and
        # password in two clubs, which is what makes login ask "which club?".
        'shared': [('member01', 'Aarav Sharma'), ('member02', 'Diya Patel'), ('member03', 'Vivaan Reddy'),
                   ('member04', 'Isha Menon'), ('member05', 'Aditya Singh')],
        'plans': [('Builder', 40000, 10), ('Maker Pro', 75000, 20)],
        'events': [
            # (title, description, venue, days from now, capacity, public, member, sold, checked in)
            ('Line Follower Showdown', 'Autonomous bots race the track.', 'Robotics Lab 1', -20, 30, 20000, 15000, 14, 12),
            ('Arduino Bootcamp', 'A weekend of sensors, motors and code.', 'Maker Space', 12, 24, 50000, 35000, 9, 0),
            ('Robo Wars Qualifier', 'Bring your bot. Safety briefing at the door.', 'Main Quad', 28, 40, 30000, 20000, 0, 0),
        ],
        'products': [
            ('Robotics Hoodie', 110000, 'Black fleece with the circuit crest.', pixel_art.HOODIE_PNG, 'apparel', {'S': 6, 'M': 8, 'L': 6, 'XL': 4}, 'M'),
            ('Soldering Mug', 28000, 'For coffee, not flux.', pixel_art.MUG_PNG, 'drinkware', {'ONE': 15}, 'ONE'),
            ('Sticker Sheet', 6000, 'Gears, bots and resistors.', pixel_art.STICKERS_PNG, 'stationery', {'ONE': 40}, None),
        ],
        'more_products': [
            ('Team Jersey', 65000, 'Breathable jersey with your name on the back.', pixel_art.T_SHIRT_PNG, 'apparel', {'S': 5, 'M': 8, 'L': 8, 'XL': 4}),
            ('Maker Tote', 22000, 'Fits a laptop, a multimeter and lunch.', pixel_art.TOTE_PNG, 'accessories', {'ONE': 20}),
            ('Lab Notebook', 16000, 'Grid pages for schematics and build logs.', pixel_art.NOTEBOOK_PNG, 'stationery', {'ONE': 30}),
            ('Gear Pin', 10000, 'Enamel gear for your lanyard or lab coat.', pixel_art.PIN_PNG, 'accessories', {'ONE': 35}),
        ],
        'pickup': 'Robotics Lab 1, Engineering Block · Tue & Thu 4pm–6pm',
        'generated_events': (seed_events.ROBOTICS_EVENTS, 37),
        'announcements': [
            (120, 'Lab access cards', 'Members can now badge into Robotics Lab 1 until 9 pm on weekdays.', 'members'),
            (95, 'Line Follower Showdown: rules posted', 'Track width, sensor limits and the scoring sheet are on the event page.', 'all'),
            (70, 'Component Drive launched', 'Help us fund motors and batteries for the Robo Wars team.', 'all'),
            (52, 'Soldering stations upgraded', 'Four new temperature-controlled irons, thanks to last term\'s dues.', 'members'),
            (38, 'Arduino Bootcamp seats', 'Twenty-four seats, member price 350. Kits are included.', 'all'),
            (21, 'Line Follower Showdown: results', 'Twelve bots finished. Fastest clean lap: 14.2 seconds.', 'all'),
            (9, 'Robo Wars Qualifier: weigh-in times', 'Bring your bot to Lab 1 between 2 and 4 the day before.', 'all'),
            (2, 'Hoodies and jerseys in the shop', 'Order online, collect from Lab 1 on Tuesdays and Thursdays.', 'all'),
        ],
        'fundraiser': ('Component Drive', 800000, ['Sponsor outreach', 'Parts list', 'Stall at tech fest']),
        'expenses': [('Motor drivers', 180000, 'paid'), ('Track printing', 45000, 'submitted')],
    },
    'music': {
        'domain': 'music.test',
        'id_prefix': 'RMS',
        'leaders': ['Sahana Iyer', 'Pranav Kulkarni', 'Aditi Ghosh', 'Rahul Verma', 'Meghna Pillai'],
        'members': ['Anjali', 'Bharat', 'Charu', 'Dhruv', 'Ekta', 'Faiz', 'Gayatri', 'Hari',
                    'Indu', 'Jatin', 'Kavita', 'Lokesh', 'Madhu', 'Naveen', 'Ojas'],
        'shared': [],
        'plans': [('Listener', 30000, 10), ('Performer', 60000, 15)],
        'events': [
            ('Unplugged Evening', 'Acoustic sets under the banyan tree.', 'Amphitheatre', -15, 50, 25000, 18000, 16, 13),
            ('Raaga Night', 'Classical vocal and instrumental recital.', 'Auditorium', 18, 60, 40000, 30000, 11, 0),
        ],
        'products': [
            ('Raaga T-Shirt', 45000, 'Soft cotton with the tanpura mark.', pixel_art.T_SHIRT_PNG, 'apparel', {'S': 8, 'M': 10, 'L': 8, 'XL': 4}, 'L'),
            ('Lyric Notebook', 18000, 'Ruled on the left, staves on the right.', pixel_art.NOTEBOOK_PNG, 'stationery', {'ONE': 25}, 'ONE'),
            ('Society Pin', 12000, 'Enamel treble clef.', pixel_art.PIN_PNG, 'accessories', {'ONE': 30}, None),
        ],
        'more_products': [
            ('Society Hoodie', 105000, 'Maroon fleece with the raga wheel on the back.', pixel_art.HOODIE_PNG, 'apparel', {'S': 5, 'M': 7, 'L': 7, 'XL': 3}),
            ('Concert Tote', 20000, 'Carries sheet music without folding it.', pixel_art.TOTE_PNG, 'accessories', {'ONE': 20}),
            ('Green Room Mug', 26000, 'For the tea before the first note.', pixel_art.MUG_PNG, 'drinkware', {'ONE': 18}),
            ('Sticker Set', 7000, 'Tanpura, tabla, treble clef and friends.', pixel_art.STICKERS_PNG, 'stationery', {'ONE': 40}),
        ],
        'pickup': 'Music Room 1, Arts Block · Mon, Wed & Fri 5pm–7pm',
        'generated_events': (seed_events.MUSIC_EVENTS, 38),
        'announcements': [
            (110, 'Practice room booking', 'Music Rooms 1 and 2 can be booked by members in one-hour slots.', 'members'),
            (90, 'Auditions for the ensemble', 'Vocal and instrumental, all traditions. Bring one piece under three minutes.', 'all'),
            (66, 'Instrument Fund launched', 'We are raising money for a second tabla set and a harmonium service.', 'all'),
            (48, 'Unplugged Evening: line-up', 'Eight acts, twelve minutes each, under the banyan tree.', 'all'),
            (30, 'Tabla repaired and back', 'Thank you to everyone who gave to the Instrument Fund so far.', 'members'),
            (16, 'Unplugged Evening: thank you', 'Sixteen tickets sold and not one broken string.', 'all'),
            (7, 'Raaga Night tickets', 'Sixty seats in the auditorium. Members pay 300.', 'all'),
            (1, 'New in the shop', 'Hoodies, totes, mugs and stickers. Collect from Music Room 1.', 'all'),
        ],
        'fundraiser': ('Instrument Fund', 600000, ['Busking permits', 'Set list', 'Donation box']),
        'expenses': [('Sound engineer', 150000, 'paid'), ('Tabla repair', 60000, 'submitted')],
    },
}


@transaction.atomic
def seed_club(slug):
    """Build one club's demo data. Call inside use_club(slug), on empty
    tables. Returns the emails of its demo accounts, by role.
    """
    data = CLUB_DATA[slug]
    domain, today, now = data['domain'], timezone.localdate(), timezone.now()
    password_hash = make_password(DEMO_PASSWORD)

    def person(prefix, name, college_id, email_domain=domain):
        # _user builds addresses at Skyline's domain; this club has its own.
        user = _user(prefix, name, college_id, password_hash)
        user.email = f'{prefix}@{email_domain}'
        user.save(update_fields=['email'])
        return user

    # People ---------------------------------------------------------------
    leaders = {}
    for number, ((prefix, role), name) in enumerate(zip(LEADERS, data['leaders']), start=1):
        leaders[prefix] = person(prefix, name, f"{data['id_prefix']}-L{number:02}")
        RoleAssignment.objects.create(
            user=leaders[prefix], role=role,
            term_start=today - timedelta(days=60), term_end=today + timedelta(days=300),
        )
    members = [
        person(f'member{number:02}', f'{first} {surname}', f"{data['id_prefix']}-{number:03}")
        for number, (first, surname) in enumerate(
            zip(data['members'], ['Nair', 'Shah', 'Das', 'Rao', 'Jain'] * 3), start=1,
        )
    ]
    shared = [
        person(prefix, name, f'SSA-{number:03}', email_domain='skyline.test')
        for number, (prefix, name) in enumerate(data['shared'], start=1)
    ]

    # Plans and memberships: everyone here is a paying member ----------------
    plans = [
        MembershipPlan.objects.create(name=name, price=price, duration_months=12, merch_discount_pct=discount)
        for name, price, discount in data['plans']
    ]
    for number, user in enumerate(members + shared + list(leaders.values())):
        purchase_membership(
            user=user, plan=plans[number % len(plans)], outcome='success',
            idempotency_key=f'seed-{slug}-dues-{number:03}',
        )

    # Events -----------------------------------------------------------------
    past_event = None
    for index, (title, description, venue, days, capacity, public, member, sold, checked_in) in enumerate(data['events']):
        starts = now + timedelta(days=days)
        event = Event.objects.create(
            title=title, description=description, venue=venue, starts_at=starts,
            ends_at=starts + timedelta(hours=3), capacity_total=capacity, status=Event.Status.ON_SALE,
            budget_amount=500000, created_by=leaders['events'],
        )
        tier = TicketTier.objects.create(
            event=event, name='General', public_price=public, member_price=member, capacity=capacity,
        )
        bought = []
        for number, buyer in enumerate((members + shared)[:sold]):
            bought.extend(purchase_tickets(
                user=buyer, tier_id=tier.pk, quantity=1, outcome='success',
                idempotency_key=f'seed-{slug}-event{index}-{number:03}',
            ).tickets)
        for ticket in bought[:checked_in]:
            tickets.scan(operator=leaders['events'], token=ticket.qr_token, event_id=event.pk)
        if days < 0:
            Event.objects.filter(pk=event.pk).update(status=Event.Status.CLOSED)
            past_event = event

    # The rest of the calendar: bulk-created catalogue events, of which three
    # past ones and one upcoming one get a small tier that members really
    # buy out (5 tickets each; 4 of 5 checked in on the past ones).
    templates, count = data['generated_events']
    generated = seed_events.build_events(templates, count, now, leaders['events'])
    past_generated = [event for event in generated if event.status == Event.Status.CLOSED]
    upcoming_generated = [event for event in generated if event.status == Event.Status.ON_SALE]
    for number, event in enumerate(past_generated[2::6][:3] + upcoming_generated[1:2]):
        is_past = event.status == Event.Status.CLOSED
        # Sold while on sale, then closed again: a closed event refuses purchases.
        Event.objects.filter(pk=event.pk).update(status=Event.Status.ON_SALE)
        tier = seed_events.add_small_tier(event, name='Members Block')
        bought = []
        for buyer_number, buyer in enumerate(members[:5]):
            bought.extend(purchase_tickets(
                user=buyer, tier_id=tier.pk, quantity=1, outcome='success',
                idempotency_key=f'seed-{slug}-extra{number}-{buyer_number:02}',
            ).tickets)
        if is_past:
            for ticket in bought[:4]:
                tickets.scan(operator=leaders['events'], token=ticket.qr_token, event_id=event.pk)
            Event.objects.filter(pk=event.pk).update(status=Event.Status.CLOSED)

    seed_events.build_announcements(
        data['announcements'], [leaders['president'], leaders['events'], leaders['volunteers']], now,
    )

    # Merchandise ------------------------------------------------------------
    catalogue = data['products'] + [(*product, None) for product in data['more_products']]
    for index, (name, price, description, picture, category, sizes, sold_size) in enumerate(catalogue):
        product = Product.objects.create(
            name=name, base_price=price, description=description, category=category, pickup_location=data['pickup'],
        )
        # A fixed file name per club and product, so re-seeding replaces the
        # picture instead of piling up copies.
        image_name = f"products/{slug}-{name.lower().replace(' ', '-')}.png"
        default_storage.delete(image_name)
        product.image.save(os.path.basename(image_name), ContentFile(picture), save=True)
        for size, quantity in sizes.items():
            row = ProductSize.objects.create(product=product, size=size)
            stock.restock(product_size=row, quantity=quantity, actor=leaders['treasurer'])
            if size == sold_size:
                for number, buyer in enumerate(members[:3]):
                    purchase_merch(
                        user=buyer, items={row.pk: 1}, outcome='success',
                        idempotency_key=f'seed-{slug}-merch{index}-{number:02}',
                    )

    # Fundraiser with tasks ----------------------------------------------------
    title, goal, task_titles = data['fundraiser']
    fundraiser = Fundraiser.objects.create(
        title=title, goal_amount=goal, starts_on=today - timedelta(days=5), ends_on=today + timedelta(days=10),
    )
    for task_title, status, owner in zip(task_titles, ['done', 'doing', 'todo'], [members[0], members[1], leaders['volunteers']]):
        task = Task.objects.create(
            fundraiser=fundraiser, title=task_title, status=status, due_date=today + timedelta(days=4),
        )
        TaskAssignment.objects.create(task=task, user=owner)
    for amount, note in [(goal // 5, 'Day 1'), (goal // 8, 'Online')]:
        record_sale(fundraiser=fundraiser, amount=amount, recorded_by=leaders['volunteers'], note=note)

    # Expenses: one paid, one waiting for the treasurer -------------------------
    for number, (description, amount, outcome) in enumerate(data['expenses']):
        request = ExpenseRequest(
            requester=members[5 + number], amount=amount, description=description,
            category='event', event=past_event,
        )
        request.receipt_file.save('receipt.png', ContentFile(_placeholder_receipt()), save=True)
        if outcome == 'paid':
            expenses.approve(request.pk, leaders['treasurer'], 'Receipt matches')
            expenses.mark_paid(request.pk, leaders['approver'])

    return {
        'leaders': {prefix: user.email for prefix, user in leaders.items()},
        'member': members[0].email,
        'shared': [user.email for user in shared],
    }
