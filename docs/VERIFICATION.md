# Verification run, 11 Oct 2026 (06:35 to 06:45 IST)

Frontend `http://localhost:5173` against backend `:8000` (fresh `seed_demo --reset` + `setup_clubs`),
driven with Claude in Chrome. Where the UI could not show something, the same request was made
directly against the API to decide whether the cause is the backend or the frontend.

**How to read "cause":** BACKEND = the API returned wrong or missing data. FRONTEND = the API
returns the right data (checked) but the screen does not use it, or the screen does not exist yet.

**Limits of this run (10 minutes of browser time):**

- Not every account was opened in the browser. Opened: president@, treasurer@, events@, member06@,
  member34@, member37@, president@robotics.test, and one new signup. Not opened: approver@,
  volunteers@, president@music.test (their behaviour was checked through the API).
- Forms filled by the automation tool (new event, role assignment) did not submit, most likely
  because the tool's value-setting did not reach the React state. Those results are marked
  "inconclusive" rather than counted as failures.
- Sound cannot be heard through the tool.
- The OTP code is printed in the terminal running `runserver`, which this session cannot read, so
  signup was taken as far as the code screen.

## Results

| # | Item | Status | Cause | Reason | Screenshot |
|---|---|---|---|---|---|
| 1 | Signup + email OTP | PARTIAL | not a defect | Signup works, the code screen appears, a wrong code shows "Wrong code. Check the email and try again.", and Resend is disabled with a countdown ("Resend code in 59s"). Not completed with the real code (it is in the runserver terminal). | `01-otp-screen-resend-countdown.jpg`, `01-otp-wrong-code.jpg` |
| 2 | Role dashboards | PASS | | President, Treasurer, Event Manager and Member dashboards are clearly different (own tool cards and nav). approver@ and volunteers@ not opened. | `02-dashboard-president.jpg`, `02-dashboard-event-manager.jpg`, `02-dashboard-member.jpg` |
| 3 | Razorpay | PARTIAL | BACKEND (fixed) + not finished | `GET /payments/config` was 401 before login, so the frontend fell back to mock: **fixed, it is public now** and returned 200 on the logged-out login page. With that, the merch payment page shows "Razorpay Test Mode" and "Pay ₹229.50", and the Razorpay test checkout opens with the club name and the server's price. The test card's "Continue" did not advance under automation, so no payment was completed in the browser: success screen, My Orders and ledger entry are **not verified here** (they are covered by backend tests with a signed payment). Membership and ticket checkout were not opened. The specific case "page loaded before login, then log in without reloading" was not re-tested. | `03-payment-razorpay-test-mode.jpg` |
| 4 | Shop | PARTIAL | FRONTEND | 10 products, all images load, sale and member price shown with the base price struck through (Campus Mug ₹229.50 / ₹300.00). Missing: categories, any coupon field, and the order summary (only "Estimated subtotal"). Size `ONE` is shown as a size button that has to be clicked before "Add to Cart" appears. | `04-shop-list.jpg`, `04-product-one-size.jpg`, `04-cart-no-coupon.jpg` |
| 5 | Member card | PASS | | member06: card with QR, ACTIVE, plan and expiry. member34: "Your membership is expiring soon" banner. member37: card says it has lapsed and scans as "not a member". | `05-member-card.jpg`, `05-membership-expiring.jpg`, `05-membership-lapsed.jpg` |
| 6 | Check-in | PARTIAL | FRONTEND | Hidden from a plain member ("Off Limits"); events@ has it. Member card token → "Active Member, Kavya Gupta" (correct). **Group pass token → the screen says "Invalid Code or Wrong Event", but the API answered `result: "admitted"` and one person WAS admitted** (the pass went from 3/10 to 4/10). No count stepper, no "already used", no "wrong event" screens. Through the API: member37 → `not_member`, wrong event → `wrong_event`. volunteers@ not opened. | `06-checkin-pass-shown-invalid.jpg` |
| 7 | Tickets page | FAIL | FRONTEND | Still the old ticket card: one card per pass with a QR, but the price shows ₹0.00 and there is no "Admitted x / N", no ticket list and no pass detail. `GET /tickets/me` returns passes correctly: member01's Board Games pass is 10 tickets, 4 admitted (3 from the seed + 1 from this run), with a two-line check-in history. member01 could not be opened in the UI (see 19). | `07-tickets-old-card.jpg` |
| 8 | Event detail overview | PARTIAL | FRONTEND | Shown: title, date/time, venue, description, status, tier with price, member price and seats left. Not shown: organiser, capacity bar (sold / seats left / checked in), sale open, and for staff revenue and attendance % (there is a "Show Attendance & P&L" button, not opened). The API returns all of them: `organiser: Meera Nair, capacity 25, sold 10, seats_left 15, checked_in 3, revenue 50000, attendance_pct 30.0`, tier `sold 10, sale_open true`. | `08-event-detail.jpg` |
| 9 | Volunteering Kanban | PARTIAL | not fully tested | To Do / Doing / Done columns with task cards. President sees "Move to" and "+ Assign" on every card. member06 (assigned to "Table") sees "Move to" only on their own task; the others are view-only. Dragging itself and volunteers@ were not exercised. | `09-volunteering-kanban.jpg` |
| 10 | Approvals Kanban | PARTIAL | FRONTEND | It is a list with a status dropdown, not a Kanban board. Treasurer's own expense is locked ("This is your own request — you cannot approve or reject it"). Approve / Reject buttons are present on the other. Reject reason and approver@ not exercised in the UI; through the API approver@ does see the treasurer's expense in the queue. | `10-approvals-list.jpg` |
| 11 | Role invites | FAIL | FRONTEND | The Admin page still has the old "Assign Role" form and a table of assignments. No pending-invite list, no Accept / Decline screen anywhere (Settings has only font and sound). Submitting the form by automation was inconclusive. Through the API: the seeded invite for member05 is `pending`; self-invite → `400 self_assignment`; ending the only president → `400 last_president`. | `11-admin-role-form.jpg` |
| 12 | Finance | PARTIAL | not fully tested | Came In / Went Out / Net / Cash / Payable are readable; "Books reconcile" badge is green; the ledger has separate Debit and Credit columns in ₹. A totals row and Coin Trail were not checked. | `12-finance.jpg`, `12-ledger.jpg` |
| 13 | Admin audit log | PARTIAL | FRONTEND | The log loads and lists rows. The action filter offers only `role.assigned`, `expense.*`, `stock.restocked`, `savefile.*`: it lacks `role.invited`, `role.invite_declined`, `role.invite_revoked`, `role.ended` and `order.refund_due`. The API has `role.invited` rows (27 rows in total). | `13-admin.jpg` |
| 14 | Insights | PASS | | Club Health shows real figures (68; "41 of 45 … active", "30 of 35 tickets were checked in"), the break-even form and the save-file event picker load. The simulator was not run. | `14-insights.jpg` |
| 15 | My Orders | PARTIAL | FRONTEND | Line labels ("Skyline T-Shirt · S"), subtotal, discount and total are shown. No coupon is shown; there is nowhere in the UI to enter one, so no order had one. | `15-orders.jpg` |
| 16 | Button sounds | NOT TESTED | | Audio cannot be heard through the tool. A mute button is in the header (label "Unmute sound", so sound starts muted) and Settings has "Sound effects". | |
| 17 | Validation | PARTIAL | inconclusive | Signup: a bad college id shows the server's message under the field and nothing is created. Event form: inconclusive under automation (see limits). Through the API every bad input returns `400` with the `fields` map, for example `{"ends_at": "The event must end after it starts."}` and `{"amount": "Ensure this value is greater than or equal to 1.", "receipt_file": "No file was submitted."}`. Expense and coupon forms not opened. | `01-signup-college-id-error.jpg`, `17-event-form.jpg` |
| 18 | Local time | PASS | | Times are shown in IST, for example "21 Oct 2026, 6:31 am" on the event and "11 Oct 2026, 6:31 am" on orders and the audit log. (Backend: two check-in timestamps were sent in UTC with `Z`; made consistent, see below.) | `08-event-detail.jpg` |
| 19 | Clubs | FAIL | FRONTEND (expected) | Logging in as president@robotics.test returns to the login page: login succeeds, but the next request is sent without `X-Club`, gets 401, and the session ends. Through the API: president@robotics.test and president@music.test get their own events, shop and ledger (robotics cash ₹23,838.00, music ₹17,119.50, both reconcile 11/11); member01@skyline.test → `409 choose_club`; a Skyline token with `X-Club: robotics` → `401`. | `19-robotics-login-bounced.jpg` |

**Console and network:** no 4xx or 5xx on the pages opened as president (events, shop, finance,
ledger, admin, insights). One console warning: React "Each child in a list should have a unique
key" in `TicketsPage`.

**Left out on purpose:** a screenshot of the check-in page (it contained the live camera picture)
and one of the Razorpay checkout (it showed a saved phone number).

**What this run changed in the dev database:** the Board Games pass is now 4/10 admitted (not
3/10); there is an unverified account `verify150@skyline.test`; order #133 (a mug) was started and
cancelled. To get the seed's exact state back: `python manage.py seed_demo --reset` then
`python manage.py setup_clubs`.

## Backend changes made after this run

1. `GET /api/payments/config` is public (no login, any token ignored). It returns only
   `{gateway, key_id}`.
2. Check-in timestamps (`checked_in_at` on a ticket scan, `history[].at` on a pass) are sent in the
   same `+05:30` form as every other timestamp instead of UTC `Z`.

No other backend defect was found: for every PARTIAL or FAIL above, the API response was checked
and is what the contract describes.

## FOR FRONTEND (teammate)

Everything below is in `docs/API_CONTRACT.md`; section names are in quotes.

1. **Clubs ("Clubs", "POST /auth/login").** Most urgent: without it nobody outside Skyline can use
   the app.
   - `POST /api/auth/login` may answer `409 {"code":"choose_club","clubs":[{slug,name,short,color}]}`.
     Show the clubs, then repeat the login with `"club": "<slug>"` in the body.
   - A successful login returns `{token, user, club:{slug,name,short,color}}`. Store `club.slug`
     next to the token and send `X-Club: <slug>` on **every** request (put it in `httpClient`).
   - `GET /api/clubs` (public) lists the clubs; `GET /api/auth/me` now includes `club`.
   - A token is valid only with its own club's `X-Club`; anything else is `401`.

2. **Check-in with a group pass ("POST /checkin", "Group pass").** Today a pass scan is shown as
   invalid although the person is admitted.
   - Send the scanned text as `token` as now; optional `count` (1 to 10).
   - A pass answers with a different shape: `{result, pass_id, admitted, admitted_now, total,
     remaining, holder:{name}, membership_status, event:{id,name,title}, tier:{id,name}}`.
   - `result`: `admitted` (show "admitted x of total, y remaining"), `already_used`, `wrong_event`,
     `invalid`. Tell a pass answer from a ticket answer by the presence of `pass_id`/`total`.
   - `count` above what is left → `400 validation_error`, `fields.count` = "Only N left on this pass."

3. **Tickets page ("Pass object", "GET /tickets/me", "GET /tickets/passes/{id}").**
   - `GET /api/tickets/me` returns passes: `{pass_id, event:{id,name,title,starts_at,venue},
     tier:{id,name}, quantity, admitted, remaining, qr_token, tickets:[{id,code,status}], created_at}`.
     There is no `price_paid` or `code` at the top level any more, which is why the card shows ₹0.00.
   - One card per pass, one QR from `qr_token`, "Admitted `admitted` / `quantity`".
   - `GET /api/tickets/passes/{pass_id}` adds `order`, `holder:{name}`,
     `history:[{at, by, count}]`.
   - Add a `key` to the list items in `TicketsPage`.

4. **Event overview ("GET /events, GET /events/{id}").** `GET /api/events/{id}` already returns
   `organiser:{name}`, `capacity`, `sold`, `seats_left`, `checked_in`, `my_passes`, and for
   president / event manager `revenue` (paise) and `attendance_pct`. Each tier has `sold`,
   `seats_left`, `sale_open`.

5. **Coupons and order summary ("Coupons", "Order object").**
   - `POST /api/coupons/validate` `{code, applies_to: "merch"|"tickets"|"membership", amount}` →
     always 200: `{valid, discount, final_amount, reason, message}`.
   - Send `"coupon": "CODE"` with `POST /api/payments/razorpay/order` (and the mock endpoints).
     A bad coupon is `400 coupon_invalid` with the reason in `message`.
   - For the summary use the order returned by the server: `subtotal`, `discount` (everything),
     `coupon`, `coupon_discount`, `total`. Seeded codes: `WELCOME10`, `GALA50`, `MERCH20`.

6. **Shop ("Product object").** `category` and `sale_pct` are on every product. A product whose
   `sizes` is a single entry with `size: "ONE"` has no sizes: select it automatically and hide the
   picker.

7. **Role invites ("Roles and role invites").**
   - `POST /api/roles` `{user, role, term_start?, term_end?}` now returns an **invite**
     (`status: "pending"`), not an assignment. Errors: `400 self_assignment`, `409 invite_pending`,
     `409 role_already_held`.
   - `GET /api/roles/invites` (president: all; anyone else: their own).
   - `POST /api/roles/invites/{id}/accept` and `/decline` (the nominee),
     `/revoke` (president), `POST /api/roles/{id}/end` (`400 last_president`).

8. **Approvals board ("Expense object", "POST /expenses/{id}/approve, /reject, /mark-paid").** The
   data for four columns is `GET /api/expenses?status=submitted|approved|paid|rejected`. Valid moves
   only: submitted → approved or rejected, approved → paid. Reject needs `{"reason": "..."}`.
   The requester's own card: `403 self_approval`.

9. **Audit filter ("GET /audit").** Add `role.invited`, `role.invite_declined`,
   `role.invite_revoked`, `role.ended`, `order.refund_due`.

10. **Payments ("Razorpay payments").** `GET /api/payments/config` is public now, so the check on
    app load no longer gets 401. While the server is on Razorpay the mock endpoints
    (`POST /memberships`, `/events/{id}/tickets`, `/orders`) answer `409 gateway_not_enabled`; use
    `POST /api/payments/razorpay/order` → Razorpay Checkout → `POST /api/payments/razorpay/verify`
    (or `/cancel` when the checkout is closed).

11. **Validation errors ("Errors").** Every `400 validation_error` has
    `fields: {"<field>": "<message>"}` (nested as `items.0.quantity`; `_` for errors with no field),
    ready to show under each input.
