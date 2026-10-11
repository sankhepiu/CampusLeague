# Campus League

**Run your club, earn your league.** One app for the Skyline Student Association to run
memberships, events and tickets, a merch shop, volunteering, announcements and
reimbursements, with every rupee recorded in one append-only, double-entry ledger.

Built at the **Odoo x NMIT Hackathon 2026** (Student Organization System problem) by
**Pruthvi Sankhe** (backend) and **Nirvana Das** (frontend).

---

## What it does

| Area | What you can do |
|---|---|
| **Accounts** | Sign up (choosing your club) with email OTP verification (hashed codes, 10-minute expiry, attempt limit, resend throttle). Role-based access: president, treasurer, event manager, volunteer coordinator, member, each with its own dashboard. |
| **Membership** | Buy or renew a plan, member-only prices, a member card with a signed QR code, automatic expiry handling. |
| **Events & tickets** | Ticket tiers with public and member prices, sale windows, capacity that can never be oversold. **One QR per order** (a group pass) that is scanned once per person ("Admitted 4 of 10"). Check-in for event managers and volunteer coordinators, with manual code entry as a fallback. |
| **Shop** | Merch with sizes and stock, sale prices, member discount and coupons (percent or flat, minimum order, cap, usage limits) on merch, tickets and memberships. A limit of 10 per item. |
| **Payments** | **Razorpay (test mode)** with server-side signature verification, or a built-in mock gateway when offline. Idempotency keys stop double charges. |
| **Volunteering** | Fundraisers with goals and progress, plus a **Kanban board** (To Do / Doing / Done) with drag and drop for assignees and coordinators. |
| **Reimbursements** | Members submit expenses with receipts. Treasurers approve on an **approvals Kanban**; nobody can approve their own expense. |
| **Finance** | Append-only double-entry ledger, live reconciliation (11 checks), and **Coin Trail**: click any figure to see the ledger lines behind it. |
| **Insights** | Break-even simulator, forecast vs actual, an explainable Club Health score, handover "Save Files". |
| **Governance** | Role changes are maker–checker: the president invites, the nominee accepts, and the last president can't be removed. Active, upcoming and ended roles are shown separately. Full audit log. |
| **More clubs** | Three clubs on one site (Skyline, Pixel Robotics, Raaga Music), **one PostgreSQL schema per club**. Same login page; you pick your club when signing up, a user in two clubs picks one after logging in, and the navbar badge shows which club you're in. Each club's ledger reconciles on its own. |

## How the money stays correct

- **Paise, not floats:** every amount is an integer number of paise.
- **Double entry:** every sale, approval and payout is a balanced entry (debits = credits).
  A PostgreSQL trigger rejects an unbalanced entry.
- **Append-only:** triggers block `UPDATE` and `DELETE` on ledger rows, so mistakes are fixed
  with a reversing entry, never by editing history.
- **No overselling:** row locks (`SELECT … FOR UPDATE`), conditional updates and DB `CHECK`
  constraints guard seats, stock, coupon limits and group-pass check-ins. Concurrency tests
  race two buyers for the last seat.
- **One transaction per purchase:** payment, order, tickets or stock, and the ledger entry
  are saved together or not at all (ACID).

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, Django 6, Django REST Framework, token auth |
| Database | PostgreSQL 17 (Docker Compose) |
| Frontend | React, TypeScript, Vite |
| Payments | Razorpay test mode (stdlib HTTP, HMAC-SHA256 verification) + mock gateway |
| Testing | Django test suite: **780+ tests**, including concurrency, a permission matrix (every endpoint × every role) and validation rules |

## Run it locally

You need Docker, Python 3.13+ and Node 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in SECRET_KEY; Razorpay keys are optional
docker compose up -d --wait     # PostgreSQL on localhost:5433
python manage.py migrate
python manage.py seed_demo --reset
python manage.py setup_clubs --reset   # extra clubs: robotics and music
python manage.py runserver      # http://127.0.0.1:8000

# 2. Frontend (new terminal)
cd frontend
cp .env.example .env
npm install
npm run dev                     # http://localhost:5173
```

Email codes print in the `runserver` terminal unless SMTP settings are filled in `.env`.
Leave `PAYMENT_GATEWAY=mock` to run without internet; set it to `razorpay` with test keys
to use Razorpay Checkout.

More detail: [`backend/README.md`](backend/README.md), [`frontend/README.md`](frontend/README.md).
The full API is documented in [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md).

## Demo accounts

Password for every demo account: `skyline-demo-2026`

| Account | Role |
|---|---|
| `president@skyline.test` | President |
| `treasurer@skyline.test` | Treasurer (has a pending expense of their own) |
| `approver@skyline.test` | Second treasurer (approves the treasurer's expense) |
| `events@skyline.test` | Event manager |
| `volunteers@skyline.test` | Volunteer coordinator |
| `member06@skyline.test` | Active member |
| `member34@skyline.test` | Membership expiring soon |
| `member37@skyline.test` | Lapsed member |
| `member01@skyline.test` | Member of two clubs (Skyline and Robotics) |
| `president@robotics.test`, `president@music.test` | Presidents of the other clubs |

The other clubs follow the same pattern (`treasurer@robotics.test`, `events@music.test`, …).
Signing up asks which club to join; the verification code is printed in the `runserver` terminal.

## Tests

```bash
cd backend && source .venv/bin/activate
python manage.py test
```

## Project structure

```
backend/    Django apps: accounts, members, events, shop, finance, volunteering,
            comms, audit, insights, common (seed, clubs, validation)
frontend/   React app, one folder per feature, each with real and mock API clients
docs/       API contract and verification report
```

## Credits

- The frontend's retro visual style is adapted from Nirvana Das's personal portfolio project
  (NES.css-based pixel theme). The club features, screens and all backend code were built
  during the hackathon.
- Pixel-art product images are generated by the seed script.
- Payments use Razorpay in **test mode only**; no real money moves.

## Future work

Razorpay webhooks and automatic refunds, scheduled jobs for every club, a deployed demo,
and a mobile-friendly check-in scanner.
