# Campus League backend

Django + Django REST Framework on PostgreSQL. The API contract is in
[`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

## Requirements

- Python 3.12 or newer (developed on 3.14)
- Docker with Compose (Docker Desktop or Colima). The database runs in a
  container; nothing else needs Docker.

## First-time setup

Run everything from the `backend/` folder.

```bash
# 1. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Local settings (never commit .env)
cp .env.example .env
```

Open `.env` and replace both `change-me` values:

- `DJANGO_SECRET_KEY`: generate one with
  `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`
- `POSTGRES_PASSWORD`: any password; it only protects your local database.

```bash
# 3. Database (PostgreSQL 17 on localhost:5433)
docker compose up -d --wait

# 4. Tables
python manage.py migrate
```

## Everyday commands

```bash
source .venv/bin/activate
docker compose up -d --wait        # start the database
python manage.py runserver         # API at http://127.0.0.1:8000/api/
python manage.py test              # run all tests (uses a throwaway database)
docker compose stop                # stop the database, keep its data
```

After pulling new code, run `pip install -r requirements.txt` and
`python manage.py migrate` again.

## Demo data

```bash
python manage.py seed_demo            # on an empty database
python manage.py seed_demo --reset    # wipe everything and rebuild (about 3 seconds)
```

Builds the Skyline Student Association: one user per role plus a second
approver, 40 members (4 lapsed, 4 expiring soon), Basic and Plus plans, a past
event with sales and check-ins, the Spring Gala with 12 General seats left,
a small meetup, a hoodie and a T-shirt in four sizes (hoodie XL has 1 left),
two past announcements, a bake-sale fundraiser with tasks, eight expense
requests (two left pending: one to approve live, and the treasurer's own to
show self-approval being refused), and a Save File for the past event. Each
role account is also a member with a gala ticket and a merch order, and the
two products have generated pixel-art pictures. Memberships and tickets are bought through the real
purchase code, so every rupee has an order, a payment and a ledger entry.
The logins are printed at the end. Priya is deliberately absent: sign her up
live.

`--reset` deletes **all** users, orders, tickets, ledger and audit rows, and
the uploaded receipts in `media/receipts/`. It
only runs when `DJANGO_DEBUG=true`.

## Demo walkthrough script

```bash
python manage.py seed_demo --reset
python manage.py runserver          # in another terminal
scripts/demo.sh
```

Eleven requests over real HTTP, each printed with a caption and its status
code: server-side pricing, idempotent retry, role check at the door, forged
QR, double scan, last-item stock, self-approval, reconciliation and the Coin
Trail. It exits non-zero if any status is not the expected one. Run it on a
fresh seed: it buys the last hoodie XL. Set `BASE=http://host:port` if the
server is elsewhere.

## Email and verification codes

New accounts must confirm a 6-digit code sent to their email before they can
log in. Seeded demo accounts are already verified.

By default emails (verification codes, renewal reminders, announcements) are
**printed in the terminal running `runserver`**; copy the code from there.
To send real email, set these in `backend/.env` (never in `.env.example` or
anywhere else in the repository):

```
EMAIL_HOST=smtp.your-provider.example
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=Campus League <you@your-domain.example>
```

Leaving `EMAIL_HOST` blank switches back to the terminal.

## Admin: roles and plans

Membership plans can be edited in the Django admin (prices are in paise:
Rs 500 = 50000). Events, tickets, orders, stock, expenses, the ledger, save
files and the audit log are visible there too, with amounts in rupees, but
**read-only**: they change only through the app. The seed creates an admin
login (`admin@skyline.test`); to make another:

```bash
python manage.py createsuperuser   # asks for email, name, college ID, password
```

Then open http://127.0.0.1:8000/admin/ and add a **Role assignment** for a
user. A role is current while today is between its term start and term end.

## Daily membership job

```bash
python manage.py run_membership_job
```

Marks memberships past their end date as lapsed and emails renewal reminders
14 and 3 days before expiry (once per window, however often it runs). Emails
are printed to the terminal in development. In production, schedule it once
a day (cron); for the demo, run it by hand.

## Announcement emails

Posting an announcement emails it straight away. Emails are printed to the
terminal in development. To retry any that failed (up to 3 attempts each):

```bash
python manage.py send_announcements
```

## The ledger is append-only

`finance_ledgerentry`, `finance_ledgerline` and `audit_auditlog` rows cannot be
updated or deleted, even from the admin or a database shell: PostgreSQL triggers refuse
it. Mistakes are corrected with a reversal entry, never by editing. To clear
local test purchases, reset the whole local database:
`docker compose down -v`, then start it and run `migrate` again.

## Troubleshooting

- **`KeyError: 'DJANGO_SECRET_KEY'`**: `backend/.env` is missing or incomplete.
- **`connection refused` on port 5433**: the database is not running; run
  `docker compose up -d --wait`.
- **`password authentication failed`**: `POSTGRES_PASSWORD` changed after the
  database was first created. `docker compose down -v` deletes the local
  database (all local data is lost); then start it again and re-run `migrate`.
- **Port 5433 already in use**: change `POSTGRES_PORT` in `.env`.
