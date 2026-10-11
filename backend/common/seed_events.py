"""Bulk demo events and announcements, shared by every club's seed.

Everything here is deterministic (no random numbers): the same seed always
builds the same events on the same relative days, so tests can assert on it.

Events and tiers are written with bulk_create: they are plain catalogue
rows with no money behind them, so there is nothing for the purchase code
to do. Tickets are NOT created here. The few sales and check-ins on these
events are made by the caller through purchase_tickets and tickets.scan, so
every one has a real order, payment and ledger entry and reconciliation
still holds.
"""
from datetime import timedelta

from comms.models import Announcement
from events.models import Event, TicketTier

# (kind, title, venue, description). {n} is replaced by an edition number
# when a title has to be used more than once.
SKYLINE_EVENTS = [
    ('workshop', 'Resume Building Workshop', 'Career Cell, Room 104', 'Bring a draft; leave with a one-page resume recruiters can read in ten seconds.'),
    ('workshop', 'Public Speaking Bootcamp', 'Seminar Hall B', 'Three hours of short talks, feedback and a lot less fear of the microphone.'),
    ('workshop', 'Intro to Git and GitHub', 'Computer Lab 3', 'Commits, branches and pull requests, hands on. Laptops required.'),
    ('workshop', 'Excel for Club Treasurers', 'Computer Lab 1', 'Budgets, pivot tables and how to stop losing receipts.'),
    ('workshop', 'Photography Basics', 'Media Room', 'Exposure, composition and a photo walk around campus.'),
    ('workshop', 'First Aid and CPR', 'Health Centre', 'Certified trainers, practice dummies, a card at the end.'),
    ('workshop', 'Design with Figma', 'Computer Lab 2', 'From a blank frame to a clickable prototype in one afternoon.'),
    ('workshop', 'Personal Finance 101', 'Seminar Hall A', 'Budgeting, SIPs and what a credit score actually is.'),
    ('talk', 'Alumni Talk: Life After Skyline', 'Auditorium', 'Three graduates on first jobs, higher studies and what they wish they had known.'),
    ('talk', 'Founder Fireside', 'Seminar Hall A', 'A campus founder on raising a first round and almost running out of money.'),
    ('talk', 'Careers in Public Policy', 'Seminar Hall B', 'What the work looks like day to day, and how to get in.'),
    ('talk', 'Mental Health on Campus', 'Auditorium', 'An open conversation with the counselling centre. Questions welcome, anonymous if you like.'),
    ('talk', 'Research Showcase', 'Library Hall', 'Ten final-year projects in five minutes each.'),
    ('talk', 'Study Abroad Info Session', 'Seminar Hall A', 'Deadlines, tests, scholarships and visas, from students who did it.'),
    ('social', 'Open Mic Night', 'Open Air Theatre', 'Poetry, comedy, music. Sign up at the door; five minutes each.'),
    ('social', 'Movie Night Under the Stars', 'Main Lawn', 'Bring a blanket. Popcorn is on the association.'),
    ('social', 'Karaoke Friday', 'Student Centre, Room 2', 'No talent required. Enthusiasm strongly encouraged.'),
    ('social', 'Chai and Chess', 'Student Centre Lawn', 'Casual games, a blitz ladder and unlimited chai.'),
    ('social', 'Cultural Potluck', 'Dining Hall Annexe', 'Bring a dish from home and the story that goes with it.'),
    ('social', 'Trivia Night', 'Student Centre, Room 2', 'Teams of four. General knowledge, campus lore and one very hard music round.'),
    ('social', 'Sunrise Trek', 'Meet at Main Gate, 4:30 am', 'A two-hour climb, breakfast at the top, back before first lecture.'),
    ('sports', 'Inter-Department Cricket', 'Main Ground', 'Ten overs a side, tennis ball, department pride on the line.'),
    ('sports', 'Five-a-Side Football', 'Turf Court', 'Knockout format. Register a squad of seven.'),
    ('sports', 'Badminton Doubles Open', 'Indoor Sports Hall', 'Mixed and same-gender draws. Shuttles provided.'),
    ('sports', 'Campus 5K Run', 'Start at Clock Tower', 'Timed run around the campus loop. Walkers welcome.'),
    ('sports', 'Table Tennis Ladder', 'Student Centre, Games Room', 'Challenge anyone above you. Top of the ladder at 6 pm wins.'),
    ('sports', 'Yoga on the Lawn', 'Main Lawn', 'A beginner-friendly hour. Mats provided for the first thirty.'),
    ('hackathon', 'Skyline Hack', 'Innovation Lab', 'Twenty-four hours, teams of up to four, problem statements from campus offices.'),
    ('hackathon', 'Design Sprint', 'Innovation Lab', 'One real problem, one day, a prototype by evening.'),
    ('hackathon', 'Data Dive', 'Computer Lab 3', 'Open datasets, a question of your own, and prizes for the clearest chart.'),
    ('hackathon', 'Code Golf Evening', 'Computer Lab 2', 'Shortest correct program wins. Bring your worst habits.'),
    ('fest', 'Diwali Mela', 'Main Quad', 'Stalls, lights, rangoli and a very competitive sweets table.'),
    ('fest', 'Holi on the Lawn', 'Main Lawn', 'Organic colours, music and water guns. White clothes advised.'),
    ('fest', 'Food Festival', 'Main Quad', 'Twenty student-run stalls. Come hungry.'),
    ('fest', 'Battle of the Bands', 'Open Air Theatre', 'Six campus bands, one trophy, judged by the crowd.'),
    ('fest', 'Winter Carnival', 'Main Quad', 'Games, a bonfire and hot chocolate by the litre.'),
    ('fest', 'Farewell Evening', 'Skyline Convention Hall', 'A send-off for the graduating batch: awards, a slideshow and dinner.'),
]

ROBOTICS_EVENTS = [
    ('workshop', 'Soldering 101', 'Robotics Lab 1', 'Through-hole and a first attempt at surface mount. Safety glasses provided.'),
    ('workshop', 'Intro to ROS 2', 'Maker Space', 'Nodes, topics and a simulated robot you can drive by the end.'),
    ('workshop', 'PCB Design with KiCad', 'Computer Lab 2', 'From schematic to a board you could actually order.'),
    ('workshop', '3D Printing Clinic', 'Maker Space', 'Bring an STL. We will get it off the bed in one piece.'),
    ('workshop', 'Computer Vision with OpenCV', 'Robotics Lab 2', 'Colour tracking, contours and a line detector for your bot.'),
    ('workshop', 'PID Tuning Hands-on', 'Robotics Lab 1', 'Make a wobbling line follower stop wobbling.'),
    ('workshop', 'Raspberry Pi Bring-up', 'Maker Space', 'Flash, boot, blink, and talk to a sensor over I2C.'),
    ('talk', 'Drones: Rules and Reality', 'Seminar Hall A', 'What you can fly, where, and what the paperwork looks like.'),
    ('talk', 'From College Team to Robotics Startup', 'Seminar Hall B', 'An alumna on turning a competition robot into a product.'),
    ('talk', 'How Mars Rovers Navigate', 'Auditorium', 'Autonomy when the nearest engineer is twenty light-minutes away.'),
    ('talk', 'Careers in Embedded Systems', 'Seminar Hall A', 'What firmware engineers do all day, and how to become one.'),
    ('social', 'Build Night', 'Maker Space', 'Open bench, shared tools, pizza at nine.'),
    ('social', 'Robot Movie Marathon', 'Seminar Hall B', 'Three films, one vote on the most plausible robot.'),
    ('social', 'Teardown Tuesday', 'Robotics Lab 2', 'We take apart a dead appliance and work out why it died.'),
    ('sports', 'Robo Soccer League', 'Main Quad', 'Two-a-side wheeled bots. Round-robin, then finals.'),
    ('sports', 'Drone Racing Time Trial', 'Indoor Sports Hall', 'Micro drones, a gate course, fastest clean lap wins.'),
    ('sports', 'Sumo Bot Showdown', 'Robotics Lab 1', 'Five hundred grams, ten centimetres, one ring.'),
    ('hackathon', 'Hardware Hack Weekend', 'Maker Space', 'Thirty-six hours and a box of parts. Build something that moves.'),
    ('hackathon', 'Maze Solver Challenge', 'Robotics Lab 1', 'Micromouse rules. Fastest run to the centre.'),
    ('hackathon', 'Automation Jam', 'Innovation Lab', 'Automate one annoying thing on campus in a day.'),
    ('fest', 'Robotics Expo', 'Main Quad', 'Every team, every robot, open to the whole campus.'),
    ('fest', 'Tech Fest: Pixel Arena', 'Skyline Convention Hall', 'Our flagship: competitions, demos and the Robo Wars final.'),
]

MUSIC_EVENTS = [
    ('workshop', 'Vocal Warm-ups and Breath', 'Music Room 1', 'Twenty minutes a day that change how you sound.'),
    ('workshop', 'Guitar for Absolute Beginners', 'Music Room 2', 'Three chords and your first song. Guitars available to borrow.'),
    ('workshop', 'Tabla Basics', 'Music Room 1', 'Teental, a simple kaida and how to sit without your legs going numb.'),
    ('workshop', 'Home Recording on a Budget', 'Media Room', 'One microphone, free software, a clean take.'),
    ('workshop', 'Reading Sheet Music', 'Music Room 2', 'Staff, clefs and rhythm, with no prior theory.'),
    ('workshop', 'Songwriting Circle', 'Music Room 1', 'Bring a verse. Leave with a chorus.'),
    ('workshop', 'Harmonium and Raga Basics', 'Music Room 1', 'Yaman and Bhupali: the notes, the mood and a simple bandish.'),
    ('talk', 'A Playback Singer on the Studio', 'Auditorium', 'How a film song is actually recorded, take by take.'),
    ('talk', 'Listening Session: Hindustani Greats', 'Library Hall', 'Four recordings, what to listen for, and why they matter.'),
    ('talk', 'The Business of Indie Music', 'Seminar Hall A', 'Streaming money, live shows and keeping your rights.'),
    ('talk', 'Carnatic and Hindustani: A Conversation', 'Seminar Hall B', 'Two performers on what the traditions share and where they part.'),
    ('social', 'Jam Night', 'Music Room 2', 'Bring an instrument or just your voice. No setlist.'),
    ('social', 'Antakshari Evening', 'Student Centre, Room 2', 'Teams, a buzzer and decades of film songs.'),
    ('social', 'Vinyl and Chai', 'Student Centre Lawn', 'A record player, a crate of LPs and a kettle.'),
    ('social', 'Karaoke Classics', 'Student Centre, Room 2', 'Sing the song you only sing in the shower.'),
    ('sports', 'Band Relay Challenge', 'Open Air Theatre', 'Swap instruments every verse. Chaos is the point.'),
    ('hackathon', 'Compose in a Day', 'Media Room', 'A theme at ten, a finished track by six.'),
    ('hackathon', 'Remix Battle', 'Media Room', 'One stem pack, twelve hours, crowd vote.'),
    ('fest', 'Monsoon Ragas', 'Auditorium', 'An evening of Malhar: vocal, sitar and flute.'),
    ('fest', 'Sufi Night', 'Open Air Theatre', 'Qawwali under the sky. Seating on the floor; cushions provided.'),
    ('fest', 'Battle of the Bands: Raaga Edition', 'Open Air Theatre', 'Fusion bands only. Classical roots required.'),
    ('fest', 'Annual Concert', 'Skyline Convention Hall', 'The whole society on one stage, from solo vocal to full ensemble.'),
]

# Ticket prices by kind: (public, member) in paise for the first tier.
PRICES = {
    'workshop': (15000, 10000), 'talk': (8000, 5000), 'social': (12000, 8000),
    'sports': (10000, 6000), 'hackathon': (25000, 18000), 'fest': (40000, 30000),
}
CAPACITY = {'workshop': 30, 'talk': 120, 'social': 60, 'sports': 80, 'hackathon': 48, 'fest': 200}


def build_events(templates, count, now, organiser, span_days=180):
    """Create `count` events spread evenly from span_days ago to span_days
    ahead, each with one to three tiers. Returns them oldest first.

    Past events are closed. Of the upcoming ones every seventh is still a
    draft and the rest are on sale. Nothing is sold: sold_count stays 0, so
    seats and tickets agree (the reconciliation check).
    """
    events, step = [], (2 * span_days) / count
    for index in range(count):
        kind, title, venue, description = templates[index % len(templates)]
        edition = index // len(templates)
        # Half a step in from each end, and an hour that varies, so no two
        # events share a start time and none lands exactly on "now".
        days = -span_days + (index + 0.5) * step
        starts = (now + timedelta(days=days)).replace(minute=0, second=0, microsecond=0) + timedelta(hours=index % 5)
        status = Event.Status.CLOSED if days < 0 else (Event.Status.DRAFT if index % 7 == 3 else Event.Status.ON_SALE)
        capacity = CAPACITY[kind]
        events.append(Event(
            title=title if edition == 0 else f'{title} #{edition + 1}',
            description=description, venue=venue, starts_at=starts,
            ends_at=starts + timedelta(hours=24 if kind == 'hackathon' else 3),
            capacity_total=capacity, status=status, budget_amount=capacity * 5000, created_by=organiser,
        ))
    Event.objects.bulk_create(events)

    tiers = []
    for index, (event, template) in enumerate(zip(events, [templates[i % len(templates)] for i in range(count)])):
        public, member = PRICES[template[0]]
        capacity = event.capacity_total
        shape = index % 3          # one, two or three tiers
        if shape == 0:
            tiers.append(TicketTier(event=event, name='General', public_price=public, member_price=member, capacity=capacity))
        elif shape == 1:
            tiers.append(TicketTier(event=event, name='Early Bird', public_price=public * 8 // 10, member_price=member * 8 // 10,
                                    capacity=capacity // 3, sale_closes=event.starts_at - timedelta(days=7)))
            tiers.append(TicketTier(event=event, name='General', public_price=public, member_price=member,
                                    capacity=capacity - capacity // 3))
        else:
            tiers.append(TicketTier(event=event, name='General', public_price=public, member_price=member, capacity=capacity * 6 // 10))
            tiers.append(TicketTier(event=event, name='Group of 4', public_price=public * 36 // 10, member_price=member * 36 // 10,
                                    capacity=capacity * 3 // 10))
            tiers.append(TicketTier(event=event, name='Front Row', public_price=public * 2, member_price=member * 2,
                                    capacity=capacity - capacity * 6 // 10 - capacity * 3 // 10))
    TicketTier.objects.bulk_create(tiers)
    return events


def add_small_tier(event, name='Limited', capacity=5, public_price=15000, member_price=10000):
    """A tier small enough for the seed to sell out with real purchases."""
    Event.objects.filter(pk=event.pk).update(capacity_total=event.capacity_total + capacity)
    return TicketTier.objects.create(
        event=event, name=name, public_price=public_price, member_price=member_price, capacity=capacity,
    )


def build_announcements(posts, authors, now):
    """Archive entries with spread-out dates, newest last in `posts`.

    Written directly (bulk_create), with no delivery rows: they stand for
    announcements from before the demo, and creating a delivery per member
    for each would only slow the seed down. The two announcements the
    Skyline seed publishes through comms.publish keep their delivery logs.
    """
    Announcement.objects.bulk_create([
        Announcement(
            title=title, body=body, audience=audience, author=authors[index % len(authors)],
            published_at=now - timedelta(days=days_ago, hours=index % 6),
        )
        for index, (days_ago, title, body, audience) in enumerate(posts)
    ])
