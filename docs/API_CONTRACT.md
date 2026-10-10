# Campus League API contract

Status: **draft, not yet reviewed by frontend.** Change this file only through
a small pull request that both of us approve.

Items marked **Assumption** fill a gap where the backend plan is silent. They
are proposals until both of us agree.

## Conventions

- Base path: `/api/`. Paths have **no trailing slash**.
- Requests and responses are JSON (`Content-Type: application/json`).
- Money is an integer number of paise.
- Dates are `YYYY-MM-DD`; timestamps are ISO 8601.
- Lists are paginated. **Assumption** (the plan does not give a format): page
  numbers, 20 per page, `?page=2` for the next page:

  ```json
  { "count": 41, "next": "http://host/api/plans?page=2", "previous": null, "results": [] }
  ```
- Fields not listed for a request are ignored.

## Authentication

Token authentication. Login and email verification return a `token`; send it
on every other request:

```
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

The server reads the user and their roles from the token. It never trusts a
user id or role sent by the client.

A user has one token. Logging in again returns the same token; logging out
deletes it, which ends the session on every device (**Assumption**).

## Errors

Every error has the same shape:

```json
{ "code": "not_authenticated", "message": "Authentication credentials were not provided.", "field": null }
```

| Key | Meaning |
|---|---|
| `code` | Stable, machine-readable. Branch on this, not on `message`. |
| `message` | Human-readable text that can be shown to the user. |
| `field` | The request field at fault, or `null`. |

**Assumption:** validation errors (`400`, code `validation_error`) also carry
an `errors` list with one item per problem, so a form can mark every field at
once. The top-level `message` and `field` repeat the first item.

```json
{
  "code": "validation_error",
  "message": "An account with this email already exists.",
  "field": "email",
  "errors": [
    { "field": "email", "code": "email_taken", "message": "An account with this email already exists." },
    { "field": "name", "code": "blank", "message": "This field may not be blank." }
  ]
}
```

Codes used by every endpoint:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | A field is missing or invalid. See `errors`. |
| 400 | `parse_error` | The body is not valid JSON. |
| 401 | `not_authenticated` | No token was sent. |
| 401 | `authentication_failed` | The token is unknown, logged out, or its user is inactive. |
| 403 | `permission_denied` | Logged in, but not allowed. |
| 403 | `email_not_verified` | Login only: the password is right but the email address has not been verified. |
| 404 | `not_found` | The record, or the endpoint itself, does not exist. |
| 405 | `method_not_allowed` | Wrong HTTP method. |
| 415 | `unsupported_media_type` | The body is not JSON. |
| 429 | `throttled` | Too many requests. The `Retry-After` header gives the wait in seconds. |
| 500 | `server_error` | A bug on the server. The message is generic; details are only in the server log. |

Common per-field codes inside `errors`: `required`, `blank`, `invalid`,
`max_length`.

## User object

Returned by signup, login and `/auth/me`.

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `email` | string | Always lowercase. |
| `name` | string | |
| `college_id` | string | |
| `phone` | string | `""` when not provided. |
| `roles` | string[] | Roles whose term includes today, sorted. Values: `president`, `treasurer`, `event_manager`, `volunteer_coordinator`, `member`. Empty for an ordinary user. |
| `membership_status` | string | `active`: a paid membership covers today. `lapsed`: had one, it has ended. `none`: never had one. |

Use `roles` only to decide which menus to show. The server enforces every
permission regardless. Whether someone is a paid-up member comes from
`membership_status`, not from the `member` role.

---

## POST /auth/signup

Create an account. Requirement: R1. **It no longer logs the user in:** the
email address must be verified first (**Assumption:** email verification is
beyond the backend plan).

- **Who:** Public. Limited to 10 requests per minute per IP address
  (`429 throttled` beyond that).
- **Database:** creates one unverified user and its first verification code,
  together or not at all. No token.
- **Email:** a 6-digit code is emailed to the address. If the email cannot be
  sent, signup still succeeds; use `POST /auth/resend-code`.

Request:

| Field | Type | Required | Rules |
|---|---|---|---|
| `email` | string | yes | Valid email, max 254. Stored lowercase; must be unique ignoring case. |
| `password` | string | yes | Max 128. At least 8 characters, not entirely numeric, not a common password, not too similar to the email or name. |
| `name` | string | yes | Not blank, max 150. |
| `college_id` | string | yes | Not blank, max 50. |
| `phone` | string | no | **Assumption:** 7 to 15 digits with an optional leading `+`, no spaces. |

```json
{
  "email": "priya@example.com",
  "password": "correct-horse-battery",
  "name": "Priya",
  "college_id": "SSA-001",
  "phone": "+919876543210"
}
```

Response `201`:

```json
{ "verification_required": true, "email": "priya@example.com" }
```

`email` is the address as stored (lowercase). Next step:
`POST /auth/verify-email`.

Errors: `400 validation_error`. Extra per-field codes:

| Field | Code |
|---|---|
| `email` | `email_taken` |
| `password` | `password_too_short`, `password_too_common`, `password_entirely_numeric`, `password_too_similar` |

Password-strength errors are reported only after every field passes its basic
checks, so a first response may not list them.

An email that is registered but not yet verified is also `email_taken`; that
person should verify (or resend the code), not sign up again.

## POST /auth/verify-email

Confirm the emailed code and log in. **Assumption:** beyond the backend plan.

- **Who:** Public. Limited to 30 requests per minute per IP address, shared
  with `resend-code` (`429 throttled`).
- **Database:** marks the user verified, deletes the code (single use), and
  creates the user's token.

Request:

```json
{ "email": "priya@example.com", "code": "482913" }
```

Response `200`: **exactly the body of `POST /auth/login`**:

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": {
    "id": 47,
    "email": "priya@example.com",
    "name": "Priya",
    "college_id": "SSA-041",
    "phone": "",
    "roles": [],
    "membership_status": "none"
  }
}
```

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_code` | The code is wrong. Also returned, identically, for an unknown email, an already verified account, a code that was already used, or a code replaced by a newer one. |
| 400 | `code_expired` | The code is more than 10 minutes old. |
| 429 | `too_many_attempts` | The 5th wrong attempt on this code, and every attempt after it, including the right code. Request a new code. |
| 400 | `validation_error` | `email` or `code` missing or blank. Not counted as an attempt. |
| 429 | `throttled` | More than 30 requests a minute from this IP address. |

Code rules: 6 digits; valid for 10 minutes; void after 5 wrong attempts;
single use; a newer code voids the older one. The server stores only a keyed
hash of the code.

## POST /auth/resend-code

Email a new code. **Assumption:** beyond the backend plan.

- **Who:** Public. Limited to 30 requests per minute per IP address, shared
  with `verify-email`.

Request:

```json
{ "email": "priya@example.com" }
```

Response `200`, **always**:

```json
{ "sent": true }
```

The response is identical whether or not the email belongs to an account,
the account is already verified, or a code was sent moments ago. A code is
actually emailed only for an unverified account that has not been sent one
in the last 60 seconds (signup's own email counts). Within those 60 seconds
the request is accepted and nothing is sent, so the frontend should disable
"resend" for 60 seconds after signup and after each resend.

A new code voids the previous one and resets the attempt count.

Errors: `400 validation_error` if `email` is missing; `429 throttled`.

## POST /auth/login

- **Who:** Public. Limited to 20 requests per minute per IP address
  (`429 throttled` beyond that).
- **Database:** creates the user's token if they have none.

Request:

```json
{ "email": "priya@example.com", "password": "correct-horse-battery" }
```

Response `200`: `token` and `user` (the same body as
`POST /auth/verify-email`).

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | `email` or `password` missing or malformed. |
| 401 | `invalid_credentials` | Wrong email, wrong password, or inactive account. The response is identical in all three cases. |
| 403 | `email_not_verified` | The password is correct but the email has not been verified. Returned **only after the password matches**, so it reveals nothing to someone guessing. Send the user to the code screen. |

## POST /auth/logout

- **Who:** Any logged-in user. (The plan's table lists logout as Public; the
  server needs the token to know which session to end.)
- **Database:** deletes the caller's token.

Request: no body. Response `204`, empty body.

Errors: `401 not_authenticated`, `401 authentication_failed`.

## GET /auth/me

Current user, current roles and membership status. Requirements: R1, R19.

- **Who:** Any logged-in user.
- **Database:** read only.

Response `200`: a [user object](#user-object).

```json
{
  "id": 7,
  "email": "treasurer@example.com",
  "name": "Asha",
  "college_id": "SSA-010",
  "phone": "",
  "roles": ["treasurer"],
  "membership_status": "none"
}
```

Errors: `401 not_authenticated`, `401 authentication_failed`.

---

## Plan object

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `name` | string | |
| `price` | integer | Paise. |
| `duration_months` | integer | A membership ends this many months after it starts. |
| `ticket_discount_pct` | integer | 0 to 100. Kept as the plan lists it; ticket prices use the tier's member price, not this. |
| `merch_discount_pct` | integer | 0 to 100. Applied to merchandise for active members. |

## Membership object

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `plan` | [plan object](#plan-object) | The benefits are here. |
| `status` | string | `pending`, `active`, `lapsed` or `cancelled`. |
| `start_date`, `end_date` | date | Both days are included. |

## GET /plans

Plans with price and benefits. Requirement: R2.

- **Who:** Public.
- **Database:** read only. Only active plans, cheapest first.

Response `200`: a paginated list of [plan objects](#plan-object).

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    { "id": 1, "name": "Basic", "price": 50000, "duration_months": 12, "ticket_discount_pct": 0, "merch_discount_pct": 10 },
    { "id": 2, "name": "Plus", "price": 90000, "duration_months": 12, "ticket_discount_pct": 5, "merch_discount_pct": 20 }
  ]
}
```

## POST /memberships

Buy or renew a plan. Requirements: R2, R3 (benefits start), R17 (dues reach
the ledger).

- **Who:** Any logged-in user.
- **Database:** in one transaction: an order with one line, a payment, an
  active membership, and one balanced ledger entry (debit Cash 1000, credit
  Membership dues revenue 4000). If any part fails, none of it is saved.
- **Price:** always the plan's current price, calculated on the server. Any
  price, total or user id in the body is ignored.

Required header (**Assumption:** the plan names an idempotency key but not
how it is sent):

```
Idempotency-Key: 3f1c9a52-7d0e-4a57-9b1e-2f6d0c8e4a11
```

8 to 64 letters, digits, `-` or `_`. Generate one new value (a UUID is ideal)
each time the user presses "Pay", and reuse that same value if the request is
retried after a timeout or a double click. Sending the same key again never
charges twice.

Request:

| Field | Type | Required | Rules |
|---|---|---|---|
| `plan` | integer | yes | Id of an active plan. |
| `test_outcome` | string | no | Mock gateway switch: `success` (default), `failure` or `pending`. **Assumption:** this is the plan's "test card flag". |

```json
{ "plan": 1, "test_outcome": "success" }
```

Responses:

| Status | When | Body |
|---|---|---|
| `201` | Payment succeeded. | `order` (status `paid`), `payment`, `membership`. |
| `200` | Same key as an earlier successful purchase. Nothing new was created. | Identical to the first `201` body. |
| `202` | `test_outcome: pending`. | `order` (status `pending`); `payment` and `membership` are `null`. |

```json
{
  "order": {
    "id": 12,
    "status": "paid",
    "subtotal": 50000,
    "discount": 0,
    "total": 50000,
    "payment_ref": "mock_5b1f0c3e9a7d4e2f8c6b1a0d9e8f7a6b",
    "created_at": "2026-10-10T11:42:07.123456+05:30",
    "lines": [
      { "id": 15, "kind": "membership", "label": "Basic membership", "plan": 1, "tier": null, "product_size": null, "qty": 1, "unit_price": 50000, "discount": 0 }
    ]
  },
  "payment": {
    "id": 9,
    "amount": 50000,
    "status": "succeeded",
    "gateway_ref": "mock_5b1f0c3e9a7d4e2f8c6b1a0d9e8f7a6b",
    "created_at": "2026-10-10T11:42:07.130000+05:30"
  },
  "membership": {
    "id": 4,
    "plan": { "id": 1, "name": "Basic", "price": 50000, "duration_months": 12, "ticket_discount_pct": 0, "merch_discount_pct": 10 },
    "status": "active",
    "start_date": "2026-10-10",
    "end_date": "2027-10-10"
  }
}
```

Membership dates:

- A first membership starts today and ends `duration_months` later.
- **Assumption:** a renewal bought while still covered starts the day after
  the current cover ends, so renewing early loses nothing.

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `idempotency_key_required` | The header is missing or malformed. |
| 400 | `validation_error` | `plan` missing, unknown or inactive (`does_not_exist`); `test_outcome` not one of the three values (`invalid_choice`). |
| 401 | `not_authenticated`, `authentication_failed` | |
| 402 | `payment_failed` | `test_outcome: failure`. The order is cancelled; no payment, membership or ledger entry exists. |
| 409 | `idempotency_key_reused` | The key already paid for a different plan, or belongs to another user. |

**Assumption:** a key whose attempt failed or stayed pending is not
remembered, so it may be sent again to retry. Nothing yet completes a
`pending` order.

## GET /memberships/me

My status, expiry and benefits. Requirements: R2, R3.

- **Who:** Any logged-in user. Always the caller's own membership.
- **Database:** read only.

Response `200`:

| Field | Type | Notes |
|---|---|---|
| `status` | string | `active`, `lapsed` or `none` (same as `membership_status` in the user object). |
| `membership` | [membership object](#membership-object) or `null` | The membership covering today. |
| `paid_until` | date or `null` | Last paid day, including a renewal that has not started yet. |
| `member_qr_token` | string or `null` | The member card: render it as a QR code exactly as received. `null` for someone who has never been a member. A lapsed member still gets one (it scans as `not_member`). Signed by the server and contains only the user id. |

```json
{
  "status": "active",
  "membership": {
    "id": 4,
    "plan": { "id": 1, "name": "Basic", "price": 50000, "duration_months": 12, "ticket_discount_pct": 0, "merch_discount_pct": 10 },
    "status": "active",
    "start_date": "2026-10-10",
    "end_date": "2027-10-10"
  },
  "paid_until": "2027-10-10",
  "member_qr_token": "eyJ1Ijo0N30:1vAbCd:Jx3..."
}
```

Errors: `401 not_authenticated`, `401 authentication_failed`.


## GET /members

Member list with status. Requirements: R1, R5.

- **Who:** President, treasurer or event manager. Anyone else, including a
  paid-up member, gets `403 permission_denied`.
- **Database:** read only. Every account is listed, ordered by name; 20 per
  page.

Query parameters (both optional, and they combine):

| Parameter | Meaning |
|---|---|
| `status` | `active`, `lapsed` or `none`: only accounts with that membership status. Any other value is `400 validation_error` on `status` (`invalid_choice`). |
| `search` | Text matched anywhere in the name **or** email, ignoring case. `college_id` is not searched. |

Response `200`:

```json
{
  "count": 46,
  "next": "http://host/api/members?page=2",
  "previous": null,
  "results": [
    {
      "id": 20,
      "email": "member14@skyline.test",
      "name": "Aadhya Gupta",
      "college_id": "SSA-014",
      "roles": [],
      "membership_status": "active"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `email`, `name`, `college_id` | string | |
| `roles` | string[] | Role names whose term includes today, sorted; `[]` for most people. |
| `membership_status` | string | `active`, `lapsed` or `none`, by the same rule as `/auth/me` and check-in. |

`count` reflects the filters. `GET /members/{id}` (in the plan's table) is not
built yet.

Errors: `400 validation_error`, `401 not_authenticated`, `403 permission_denied`.

---

## GET /roles, POST /roles

Assign roles with terms. Requirement: R19.

- **Who:** President only (`403 permission_denied` for everyone else,
  including a president whose term has ended or not yet started).
- **Database:** POST creates one role assignment and one audit-log row
  (`role.assigned`), together or not at all.

POST request:

| Field | Type | Required | Rules |
|---|---|---|---|
| `user` | integer | yes | Id of an existing user. |
| `role` | string | yes | `president`, `treasurer`, `event_manager`, `volunteer_coordinator` or `member`. |
| `term_start`, `term_end` | date | yes | Both days included; `term_end` not before `term_start` (`term_end_before_start`). |

Response `201`: `{ "id", "user", "role", "term_start", "term_end", "created_at" }`.
GET returns a paginated list of the same objects.

## Event and tier objects

Event:

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `title`, `description`, `venue` | string | |
| `starts_at`, `ends_at` | timestamp | |
| `capacity_total` | integer | |
| `status` | string | `draft`, `on_sale` or `closed`. **Assumption:** drafts are returned to event staff only; others get `404`. |
| `tiers` | tier[] | Cheapest first. |

Tier:

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `name` | string | Unique within the event. |
| `public_price`, `member_price` | integer | Paise. Both greater than zero (**Assumption:** no free tickets yet). |
| `price` | integer | What **the caller** would pay now: `member_price` if logged in with an active membership, otherwise `public_price`. Display this one. |
| `capacity` | integer | |
| `seats_left` | integer | For "X seats left". `0` means sold out. |
| `sale_opens`, `sale_closes` | timestamp or `null` | **Assumption:** `null` means no limit on that side. |

## GET /events, GET /events/{id}

Requirements: R6, R7, R8.

- **Who:** Public. Send the token when logged in so `price` reflects membership.
- **Database:** read only.

Response `200`: a paginated list of events, or one event.

## POST /events, PATCH /events/{id}, POST /events/{id}/tiers

- **Who:** President or event manager.
- **Event fields:** `title`, `venue`, `starts_at`, `ends_at`, `capacity_total`
  (required on create); `description`, `status` (default `draft`),
  `budget_amount` (paise, default 0, never returned by the public endpoints).
  PATCH accepts any subset. PUT is not supported.
- **Tier fields:** `name`, `public_price`, `member_price`, `capacity`
  (required); `sale_opens`, `sale_closes`.
- **Rules:** the event must end after it starts (`ends_before_start`); a
  tier's capacity must fit in what `capacity_total` has left
  (`exceeds_event_capacity`); `capacity_total` cannot be lowered below the
  tiers' total (`below_tier_capacity`); tier names are unique per event
  (`tier_name_taken`). `sold_count` cannot be set through the API.

Responses: `201` (or `200` for PATCH) with the event or tier object.
Errors: `400 validation_error`, `401`, `403 permission_denied`, `404 not_found`.

## POST /events/{id}/tickets

Buy tickets in one tier. Requirements: R6, R7, R8.

- **Who:** Any logged-in user.
- **Database:** in one transaction, with the tier row locked: seat check,
  order with one line, payment, `sold_count` increase, one ticket per seat,
  and one ledger entry (debit Cash 1000, credit Ticket revenue 4100, tagged
  with the event). If any part fails, none of it is saved.
- **Price:** decided on the server at purchase time. Any price in the body is
  ignored.
- **Header:** `Idempotency-Key`, exactly as for `POST /memberships`.

Request:

| Field | Type | Required | Rules |
|---|---|---|---|
| `tier` | integer | yes | A tier of this event. |
| `quantity` | integer | no | 1 to 10, default 1. **Assumption:** 10 is the most in one purchase. |
| `test_outcome` | string | no | `success` (default), `failure`, `pending`. |

Responses: `201` (or `200` on a replay) with `order`, `payment` and `tickets`;
`202` when pending (`tickets` is `[]`, no seat is held).

Ticket object:

```json
{
  "id": 31,
  "code": "K7MPQ2XD",
  "qr_token": "eyJ0IjozMSwiZSI6Mn0:1vAbCd:Jx3...",
  "status": "valid",
  "price_paid": 60000,
  "event": { "id": 2, "title": "Spring Gala", "venue": "Main Hall", "starts_at": "2026-11-09T18:00:00+05:30" },
  "tier": { "id": 5, "name": "General" },
  "created_at": "2026-10-10T12:30:00+05:30"
}
```

Render `qr_token` as the QR code exactly as received; do not parse it. Show
`code` as text beside it for manual entry. `status` is `valid`, `checked_in`
or `cancelled`.

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `idempotency_key_required` | Header missing or malformed. |
| 400 | `validation_error` | `tier` not part of this event (`does_not_exist`); `quantity` out of range. |
| 402 | `payment_failed` | `test_outcome: failure`. No seat taken. |
| 404 | `not_found` | No such event (or it is a draft). |
| 409 | `sold_out` | Fewer seats left than requested. Nothing was created. |
| 409 | `sales_closed` | Event not `on_sale`, or outside the tier's sale window. |
| 409 | `idempotency_key_reused` | Key already paid for a different purchase. |

## GET /tickets/me

- **Who:** Any logged-in user. Only the caller's own tickets, newest first.

Response `200`: a paginated list of ticket objects.

## POST /checkin

Scan a ticket, or a member card, at the door. Requirements: R5, R9.

- **Who:** President, event manager or volunteer coordinator, because the
  answer reveals membership status. **Assumption:** the plan lists president
  and event manager only; the volunteer coordinator is added because they
  staff the door. Treasurer and ordinary members get `403`.
- **Database:** for a valid, unused ticket: one check-in row (unique per
  ticket) and the ticket becomes `checked_in`. A member card scan writes
  nothing.

Request: exactly one of `token`, `code` or `member_token`.

| Field | Type | Notes |
|---|---|---|
| `token` | string | The scanned QR content. |
| `code` | string | The short code typed by hand; case, spaces and dashes are ignored. |
| `member_token` | string | A member card's QR content (`member_qr_token` from `GET /memberships/me`). See "Member card" below. |
| `event` | integer | Optional. **Assumption:** the event being scanned for; a ticket for any other event is `invalid`. |

Response: **always `200`** with one result object (the plan's shape):

```json
{
  "result": "ok",
  "ticket": { "id": 31, "code": "K7MPQ2XD", "status": "checked_in", "event": { "id": 2, "title": "Spring Gala" }, "tier": { "id": 5, "name": "General" } },
  "holder_name": "Priya",
  "membership_status": "active",
  "checked_in_at": "2026-11-09T18:05:12+05:30",
  "checked_in_by": "Dev"
}
```

| `result` | Meaning | Other fields |
|---|---|---|
| `ok` | Admitted now. | All set. |
| `already_checked_in` | Scanned before. Do not admit again. | `checked_in_at` and `checked_in_by` are the **original** scan; `membership_status` is as recorded then. |
| `cancelled` | Ticket was cancelled. | `ticket`, `holder_name`, `membership_status` set; check-in fields `null`. |
| `invalid` | Forged, altered, unknown, or for another event. | Everything else `null`. |

Show "Active member" only when `membership_status` is `active`; `lapsed` and
`none` are both "Not a member".

### Member card

With `member_token` the response is a different, smaller object, and no
check-in is recorded (scan it as often as you like):

```json
{
  "result": "member_ok",
  "holder": { "name": "Priya", "email": "priya@example.com" },
  "membership_status": "active"
}
```

| `result` | Meaning | `holder` | `membership_status` |
|---|---|---|---|
| `member_ok` | Active membership today. | set | `active` |
| `not_member` | The card is genuine but the membership is not active. | set | `lapsed` or `none` |
| `invalid` | Forged or altered token, or the account no longer exists. | `null` | `null` |

A ticket token sent as `member_token`, or a member token sent as `token`, is
`invalid`.

Errors: `400 validation_error` (none, or more than one, of `token`, `code`
and `member_token`), `401`, `403 permission_denied`.

## GET /events/{id}/attendance

Sold, checked in, no-shows. Requirement: R10.

- **Who:** President, event manager or treasurer.
- **Database:** read only.

```json
{
  "event": { "id": 1, "title": "Freshers Night", "status": "closed" },
  "capacity_total": 60,
  "sold": 35,
  "checked_in": 30,
  "no_shows": 5,
  "attendance_rate_pct": 85.7,
  "tiers": [
    { "id": 1, "name": "General", "capacity": 60, "sold": 35, "checked_in": 30, "no_shows": 5 }
  ]
}
```

- `sold` excludes cancelled tickets.
- **Assumption:** `no_shows` is `sold - checked_in`; it only means "did not
  come" once the event is over.
- `attendance_rate_pct` is `null` when nothing has been sold.

Errors: `401`, `403 permission_denied`, `404 not_found`.

## GET /events/{id}/pnl

Event revenue minus expenses, budget vs actual. Requirement: R10.

- **Who:** President, event manager or treasurer.
- **Database:** read only. Every figure is summed from ledger lines tagged
  with this event; nothing is stored. Amounts are paise.

```json
{
  "event": { "id": 1, "title": "Freshers Night", "status": "closed" },
  "revenue": { "total": 740000, "by_account": [ { "code": "4100", "name": "Ticket revenue", "amount": 740000 } ] },
  "expenses": { "total": 0, "by_account": [] },
  "profit": 740000,
  "budget": { "amount": 1200000, "spent": 0, "remaining": 1200000 },
  "attendance": { "sold": 35, "checked_in": 30, "attendance_rate_pct": 85.7 }
}
```

- `profit` and `budget.remaining` can be negative.
- `expenses` stays empty until reimbursements (Phase 4) post to the ledger.

Errors: `401`, `403 permission_denied`, `404 not_found`.

---

## Order object

Returned by every purchase endpoint and by `GET /orders/me`.

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `status` | string | `pending`, `paid` or `cancelled`. |
| `subtotal`, `discount`, `total` | integer | Paise. `total = subtotal - discount`, always. |
| `payment_ref` | string | Gateway reference; `""` until paid. |
| `created_at` | timestamp | |
| `lines` | line[] | |

Order line:

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `kind` | string | `membership`, `ticket` or `merch`. |
| `label` | string | What was bought, ready to display. Read-only. See below. |
| `plan`, `tier`, `product_size` | integer or `null` | The one matching `kind` is set. |
| `qty` | integer | |
| `unit_price` | integer | Per unit, before discount. |
| `discount` | integer | Total discount on this line. Paid = `qty * unit_price - discount`. |

`label` by kind (the separator is a middle dot, U+00B7, with a space either side):

| `kind` | `label` | Example |
|---|---|---|
| `membership` | Plan name + " membership" | `Plus membership` |
| `ticket` | Event title · tier name | `Spring Gala · General` |
| `merch` | Product name · size | `Skyline Hoodie · M` |

The label uses the current names, so it follows a later rename of the plan,
event, tier or product. Every endpoint that returns an order includes it:
`GET /orders/me`, `POST /orders`, `POST /memberships` and
`POST /events/{id}/tickets`.

## Product object

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `name`, `description` | string | |
| `base_price` | integer | Paise, before member discount. |
| `price` | integer | What **the caller** would pay per item now (their plan's `merch_discount_pct` applied if their membership is active). Display this one. |
| `image_url` | string or `null` | Path of the product picture relative to the site root, `/media/products/<file>.png`, to load through the frontend's `/media` proxy; `null` when there is none. Replaces the earlier `image` field. **Assumption:** there is no upload endpoint; the seed provides the pictures. |
| `active` | boolean | Inactive products are returned to shop staff only. |
| `sizes` | array | Always `S`, `M`, `L`, `XL` in that order: `{ "id", "size", "stock" }`. Use `id` when ordering. |

## GET /products

Requirements: R13, R14.

- **Who:** Public. Send the token when logged in so `price` reflects membership.

Response `200`: a paginated list of product objects.

```json
{
  "id": 1, "name": "Skyline Hoodie", "description": "Heavyweight fleece with the club crest.",
  "base_price": 120000, "price": 96000, "image_url": "/media/products/skyline-hoodie.png", "active": true,
  "sizes": [ { "id": 1, "size": "S", "stock": 8 }, { "id": 2, "size": "M", "stock": 5 },
             { "id": 3, "size": "L", "stock": 6 }, { "id": 4, "size": "XL", "stock": 1 } ]
}
```

## POST /orders

Order merchandise. Requirements: R3, R13, R14.

- **Who:** Any logged-in user.
- **Database:** in one transaction, with every ordered size row locked: stock
  check, order with one line per size, payment, stock decrease with one stock
  movement per line, and one ledger entry for the order (debit Cash 1000,
  credit Merchandise revenue 4200, at the amount actually paid). If any part
  fails, none of it is saved; one unavailable size refuses the whole basket.
- **Price and discount:** from the server only. Anything in the body is ignored.
  **Assumption:** the discount is rounded down to a whole paisa per line.
- **Header:** `Idempotency-Key`, as for `POST /memberships`.

Request:

| Field | Type | Required | Rules |
|---|---|---|---|
| `items` | array | yes | 1 to 20 entries; each size at most once (`duplicate_item`). |
| `items[].product_size` | integer | yes | A size `id` from `GET /products`. |
| `items[].quantity` | integer | no | 1 to 10, default 1. |
| `test_outcome` | string | no | `success` (default), `failure`, `pending`. |

```json
{ "items": [ { "product_size": 2, "quantity": 1 } ] }
```

Responses: `201` (or `200` on a replay) with `order` and `payment`; `202`
when pending (no stock is held).

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `idempotency_key_required`, `validation_error` | |
| 402 | `payment_failed` | `test_outcome: failure`. Stock untouched. |
| 409 | `out_of_stock` | A size has less stock than requested. `message` names the product, size and what is left. |
| 409 | `product_unavailable` | A size id does not exist or its product is inactive. |
| 409 | `idempotency_key_reused` | Key already paid for a different basket. |

## GET /orders/me

- **Who:** Any logged-in user. The caller's own orders of every kind
  (membership, tickets, merch), newest first. Pending and cancelled orders
  are included; use `status` to tell them apart.

Response `200`: a paginated list of order objects. Each line's `label` says
what was bought, so no further lookups are needed:

```json
{
  "id": 121, "status": "paid", "subtotal": 160000, "discount": 32000, "total": 128000,
  "payment_ref": "mock_5b1f0c3e9a7d4e2f8c6b1a0d9e8f7a6b", "created_at": "2026-10-10T18:20:00+05:30",
  "lines": [
    { "id": 140, "kind": "merch", "label": "Skyline Hoodie · M", "plan": null, "tier": null, "product_size": 2, "qty": 1, "unit_price": 120000, "discount": 24000 },
    { "id": 141, "kind": "merch", "label": "Skyline T-Shirt · XL", "plan": null, "tier": null, "product_size": 8, "qty": 1, "unit_price": 40000, "discount": 8000 }
  ]
}
```

## POST /products, PATCH /products/{id}, POST /products/{id}/restock

- **Who:** President, treasurer or event manager.
- **Product fields:** `name` (unique), `base_price` (required on create);
  `description`, `active`. PATCH accepts any subset. The picture and stock cannot be
  set here. **Assumption:** a new product gets all four sizes at zero stock.
- **Restock:** `{ "size": "M", "quantity": 7 }`, quantity 1 to 10000. Adds to
  stock, writes a stock movement and an audit-log row (`stock.restocked`).

Responses: the product object (`201` on create, otherwise `200`).
Errors: `400 validation_error`, `401`, `403 permission_denied`, `404 not_found`.

---

## Announcement object

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `title`, `body` | string | |
| `audience` | string | **Assumption:** `all` (every active account) or `members` (active memberships only). |
| `author` | object | `{ "id", "name" }`. |
| `published_at` | timestamp | |
| `deliveries` | object or `null` | `{ "recipients", "queued", "sent", "failed" }` for president, event manager and volunteer coordinator; `null` for everyone else. |

## GET /announcements, GET /announcements/{id}

The archive: what was said, when, and by whom. Requirement: R12.

- **Who:** Public. Newest first. Reads saved announcements, so it is complete
  even when email failed.

## POST /announcements

One post reaches everyone. Requirement: R11.

- **Who:** President, event manager or volunteer coordinator.
- **Database:** first the announcement and one delivery row per recipient are
  saved (status `queued`). Then each is emailed and its row marked `sent` or
  `failed` with the error. An email failure never loses the announcement.

Request: `title` (max 200), `body`, optional `audience` (default `all`).
The author and time are set by the server.

Response `201`: the announcement object with `deliveries` filled in. Check
`deliveries.failed` to tell the user some emails did not go out.

```json
{
  "id": 3, "title": "Hoodies restocked", "body": "All sizes back this week.", "audience": "all",
  "author": { "id": 2, "name": "Ananya Rao" },
  "published_at": "2026-10-10T13:17:02+05:30",
  "deliveries": { "recipients": 46, "queued": 0, "sent": 46, "failed": 0 }
}
```

Failed emails are retried by the server (`manage.py send_announcements`), at
most 3 attempts each. There is no retry endpoint yet. Announcements cannot be
edited or deleted.

Errors: `400 validation_error`, `401`, `403 permission_denied`.

## GET /announcements/{id}/deliveries

The delivery log. Not in the plan's endpoint table; added so the app can
"show the delivery log" as the plan asks.

- **Who:** President, event manager or volunteer coordinator (it lists email
  addresses).

Response `200`: a paginated list of
`{ "id", "recipient": { "id", "name", "email" }, "status", "attempts", "last_error", "updated_at" }`.

---

## Expense object

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `requester` | object | `{ "id", "name" }`. |
| `amount` | integer | Paise. |
| `category` | string | **Assumption:** `event`, `fundraiser` or `general`, one per expense account (5000, 5100, 5200). |
| `event`, `fundraiser` | integer or `null` | `event` category needs `event`; `fundraiser` needs `fundraiser`; `general` takes neither. |
| `description` | string | Max 500. |
| `receipt_url` | string | Path of the uploaded receipt, relative to the site root: `/media/receipts/<name>`. The same form in every expense endpoint and in the trace, so it can be loaded through the frontend's `/media` proxy. |
| `status` | string | `submitted`, `approved`, `rejected` or `paid`. |
| `created_at` | timestamp | |
| `approval` | object or `null` | `{ "decision", "reason", "decided_at", "approver": { "id", "name" } }` once decided. |

Status only ever changes through the three decision endpoints below. There is
no endpoint to edit an expense.

## POST /expenses

Submit an expense with its receipt. Requirement: R18.

- **Who:** Any logged-in user.
- **Body:** `multipart/form-data` (the one endpoint that is not JSON), fields
  `amount`, `category`, `description`, `receipt_file`, and `event` or
  `fundraiser` as the category requires.
- **Receipt:** JPG, PNG or PDF, at most 5 MB. The file's content is checked,
  not just its name. Codes on `receipt_file`: `required`,
  `unsupported_file_type`, `file_too_large`, `file_content_mismatch`.
- **Database:** one expense, always `submitted`, requester = the caller. No
  ledger entry yet.

Response `201`: the expense object. Errors: `400 validation_error` (also
`event_required`, `fundraiser_required`, `tag_not_allowed`), `401`.

## GET /expenses, GET /expenses/me

- `GET /expenses`: president or treasurer. Every request, newest first.
  Filter with `?status=submitted` for the approval queue.
- `GET /expenses/me`: any logged-in user; only their own.

Response `200`: a paginated list of expense objects.

## POST /expenses/{id}/approve, /reject, /mark-paid

Requirement: R18.

- **Who:** President or treasurer, and **never the requester** (`403
  self_approval`), even if the requester holds one of those roles.
- **Body (JSON):** `approve`: optional `reason`. `reject`: `reason` required
  (**Assumption**). `mark-paid`: no body.
- **Database:** each runs in one transaction with the request row locked,
  and writes an audit-log row.

| Action | Allowed from | Becomes | Ledger entry |
|---|---|---|---|
| `approve` | `submitted` | `approved` | Debit the expense account, credit Reimbursements payable 2000 (tagged with the event). |
| `reject` | `submitted` | `rejected` | None. |
| `mark-paid` | `approved` | `paid` | Debit Reimbursements payable 2000, credit Cash 1000. |

Response `200`: the updated expense object.

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | `reject` without a `reason`. |
| 403 | `permission_denied` | Not a current president or treasurer. |
| 403 | `self_approval` | The caller submitted this request. |
| 404 | `not_found` | |
| 409 | `invalid_status` | The action is not allowed from the current status (already decided, not yet approved, already paid). |

---

## GET /finance/summary

The one-page treasurer view. Requirement: R17.

- **Who:** President or treasurer (as for every `/finance/` endpoint).
- **Database:** read only; every figure is summed from ledger lines.

```json
{
  "came_in": { "total": 7108000, "by_account": [ { "code": "4000", "name": "Membership dues revenue", "amount": 2400000 } ] },
  "went_out": { "total": 1007000, "by_account": [ { "code": "5000", "name": "Event expenses", "amount": 992000 } ] },
  "net": 6101000,
  "cash": 6236000,
  "payable": 135000
}
```

`cash` is what is in the bank; `payable` is approved reimbursements not yet
paid. `net` differs from `cash` by exactly `payable`.

## GET /finance/ledger

Paginated ledger entries, newest first, each with its lines:

```json
{
  "id": 131, "posted_at": "2026-10-10T13:30:02+05:30", "description": "Expense approved: Venue deposit",
  "source_type": "expense_request", "source_id": 4, "kind": "expense_approved", "event": 2, "reverses": null,
  "lines": [
    { "id": 261, "account": { "code": "5000", "name": "Event expenses", "type": "expense" }, "debit": 500000, "credit": 0 },
    { "id": 262, "account": { "code": "2000", "name": "Reimbursements payable", "type": "liability" }, "debit": 0, "credit": 500000 }
  ]
}
```

Filters: `?account=<code>`, `?event=<id>`, `?kind=<kind>`. Kinds:
`membership_dues`, `ticket_sale`, `merch_sale`, `fundraiser_sale`,
`expense_approved`, `expense_paid`.

## GET /finance/reconcile

Compares ledger totals with the same figures computed from the source tables.

```json
{
  "ok": true,
  "checks": [
    { "name": "Ticket revenue equals paid ticket order lines", "ok": true, "expected": 2820000, "actual": 2820000 }
  ]
}
```

Eleven checks: ledger debits equal credits; the plan's cash identity; cash
against payments, fundraiser takings and payouts; each of the four revenue
accounts against its source records; expenses and payables against expense
requests; seats sold against tickets; stock against stock movements.

## GET /finance/trace?figure=...

The Coin Trail: a figure, the entries that make it up, their lines, and the
record behind each entry.

`figure` is one of: `came_in`, `went_out`, `cash`, `payable`,
`account:<code>`, `event:<id>:revenue`, `event:<id>:expenses`,
`event:<id>:profit`. Anything else is `400 validation_error` on `figure`
(`unknown_figure`).

```json
{
  "figure": "event:1:profit",
  "label": "Freshers Night: profit",
  "total": 290000,
  "entry_count": 38,
  "entries": [
    {
      "id": 44, "posted_at": "...", "description": "Tickets: Freshers Night / General x1", "kind": "ticket_sale",
      "amount": 30000,
      "lines": [
        { "id": 87, "account": { "code": "1000", "name": "Cash and bank" }, "debit": 30000, "credit": 0, "counted": false },
        { "id": 88, "account": { "code": "4100", "name": "Ticket revenue" }, "debit": 0, "credit": 30000, "counted": true }
      ],
      "source": {
        "type": "order_line", "id": 44, "label": "Amrita Pillai bought 1 x General for Freshers Night",
        "details": { "order": 44, "buyer": "Amrita Pillai",
                     "tickets": [ { "type": "ticket", "id": 35, "code": "C2XZ22P4", "holder": "Amrita Pillai", "price_paid": 30000, "status": "valid", "checked_in_at": null } ] }
      }
    }
  ]
}
```

- `total` equals the sum of every entry's `amount`. In a profit figure,
  expense entries have negative amounts.
- `lines` is **every** line of the entry, so its debits always equal its
  credits. `counted` is `true` for the lines on the figure's own accounts,
  the ones that make up `amount`, and `false` for the other side of the
  entry, shown for context. The same entry has different `counted` flags
  under different figures (a merch sale counts its 4200 line under
  `account:4200` and its 1000 line under `cash`).
- `entries` is newest first and capped at 200; `entry_count` is the full count.
- `source` is `{ "type", "id", "label", "details" }`. `details` by `type`:

| `source.type` | For | `details` keys |
|---|---|---|
| `payment` | Membership dues | `order`, `member`, `plan`, `membership`, `amount` |
| `order_line` | Tickets | `order`, `buyer`, `tickets` (each: `type`, `id`, `code`, `holder`, `price_paid`, `status`, `checked_in_at`) |
| `order` | Merchandise | `order` (the order id, same as `source.id`), `buyer`, `items` (each: `product`, `size`, `qty`, `unit_price`, `discount`, `paid`) |
| `expense_request` | Reimbursements | `description`, `requester`, `amount`, `status`, `receipt_url`, `approved_by` (the approver's name, or `null` if not approved) |
| `fundraiser_sale` | Fundraiser takings | `fundraiser`, `amount`, `recorded_by` |

---

## Fundraiser and task objects

Fundraiser:

| Field | Type | Notes |
|---|---|---|
| `id`, `title` | | |
| `goal_amount` | integer | Paise. |
| `starts_on`, `ends_on` | date | |
| `status` | string | **Assumption:** `planned`, `active` or `closed`. |
| `progress` | object | `{ "goal_amount", "raised_amount", "raised_pct", "tasks_total", "tasks_done", "on_track" }`. `raised_amount` is summed from the ledger. `raised_pct` is capped at 100. **Assumption:** `on_track` means the share of the goal raised is at least the share of the time elapsed. |
| `tasks` | task[] | |

Task: `{ "id", "fundraiser", "event", "title", "description", "status", "due_date", "assignees": [ { "id", "name", "role_note" } ] }`.
`status` is `todo`, `doing` or `done`. A task belongs to exactly one
fundraiser or one event.

## Volunteering endpoints

Requirements: R15, R16.

| Endpoint | Who | Notes |
|---|---|---|
| `GET /fundraisers`, `GET /fundraisers/{id}` | Any logged-in user | Tasks, owners and progress. |
| `POST /fundraisers`, `PATCH /fundraisers/{id}` | President, volunteer coordinator | `title`, `goal_amount`, `starts_on`, `ends_on`, `status`. |
| `POST /fundraisers/{id}/sales` | President, volunteer coordinator | `{ "amount", "note" }`. Records takings and posts the ledger entry (debit Cash, credit Fundraiser revenue 4300). **Not in the plan's table;** added with the sale record the plan's posting rules require. Returns the fundraiser. |
| `POST /tasks`, `PATCH /tasks/{id}` | President, volunteer coordinator | `fundraiser` or `event`, `title`, `description`, `due_date`. Status is not editable here. |
| `POST /tasks/{id}/assign` | President, volunteer coordinator | `{ "user", "role_note" }`. Assigning the same person again updates the note. |
| `PATCH /tasks/{id}/status` | An assignee of that task, president, volunteer coordinator | `{ "status" }`. Anyone else: `403 permission_denied`. |

---

## POST /simulator

Break-even Bench. A calculation only: nothing is saved and the ledger is not
touched.

- **Who:** Event manager, treasurer or president.

Request (all amounts in paise, all whole numbers of 0 or more):

| Field | Type | Required | Rules |
|---|---|---|---|
| `ticket_price` | integer | yes | Must be greater than `variable_cost_per_head`. |
| `expected_attendance` | integer | yes | **Assumption:** at most 1,000,000. |
| `fixed_costs` | integer | yes | Costs that do not depend on attendance. |
| `variable_cost_per_head` | integer | yes | Cost of one more guest. |
| `event` | integer | no | An event id. If that event has ended, the response adds forecast vs actual. |

**Assumption:** money fields are capped at 10^11 paise.

```json
{ "ticket_price": 50000, "expected_attendance": 60, "fixed_costs": 1000000, "variable_cost_per_head": 10000 }
```

Response `200`:

```json
{
  "inputs": { "ticket_price": 50000, "expected_attendance": 60, "fixed_costs": 1000000, "variable_cost_per_head": 10000 },
  "margin_per_head": 40000,
  "break_even_attendance": 25,
  "revenue": 3000000,
  "costs": 1600000,
  "profit": 1400000,
  "breaks_even": true,
  "event": null,
  "forecast_vs_actual": null
}
```

- `break_even_attendance` is `fixed_costs / (ticket_price - variable_cost_per_head)`,
  rounded **up** to a whole person.
- `revenue`, `costs` and `profit` are at `expected_attendance`. `profit` can
  be negative.
- `breaks_even` is whether `expected_attendance` reaches the break-even point.

With `event` set and the event already over, `forecast_vs_actual` is filled
from the ledger and the door (the same figures as `GET /events/{id}/pnl`):

```json
{
  "event": { "id": 1, "title": "Freshers Night" },
  "forecast_vs_actual": {
    "forecast": { "attendance": 40, "revenue": 1000000, "costs": 400000, "profit": 600000 },
    "actual": { "attendance": 30, "tickets_sold": 35, "revenue": 740000, "costs": 450000, "profit": 290000 },
    "difference": { "attendance": -10, "revenue": -260000, "costs": 50000, "profit": -310000 }
  }
}
```

- `difference` is actual minus forecast.
- **Assumption:** `actual.attendance` is people checked in; `tickets_sold` is
  given beside it because revenue follows sales.
- For an event that has not ended, `forecast_vs_actual` is `null`.

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | A field is missing, negative, not a whole number or too large; `event` does not exist. |
| 400 | `validation_error` on `ticket_price`, item code `no_break_even` | The price is not higher than the cost per head, so no attendance can break even. |
| 401, 403 | | Not logged in; not one of the three roles. |

## GET /health

Club Health: a 0 to 100 score that explains itself. (Not a server uptime
check.)

- **Who:** President only.
- **Database:** read only; everything is counted when asked.

```json
{
  "score": 68,
  "components": [
    { "key": "membership", "label": "Membership", "score": 64, "weight": 30, "contribution": 19.2,
      "reason": "41 of 45 people who joined are active members (91%); 0 of 4 whose membership ran out have renewed (0%)." },
    { "key": "attendance", "label": "Event attendance", "score": 86, "weight": 25, "contribution": 21.5,
      "reason": "30 of 35 tickets were checked in across 1 closed event(s)." },
    { "key": "volunteering", "label": "Volunteering", "score": 25, "weight": 20, "contribution": 5.0,
      "reason": "1 of 4 tasks are done." },
    { "key": "money", "label": "Money", "score": 90, "weight": 25, "contribution": 22.5,
      "reason": "In the last 30 days Rs 75,380.00 came in and Rs 8,300.00 went out; cash is now Rs 67,080.00." }
  ]
}
```

| Field | Meaning |
|---|---|
| `score` | Weighted average of the component scores, 0 to 100; `null` for a club with nothing to measure yet. |
| `components[].score` | 0 to 100, or `null` when there is no data for it. |
| `components[].weight` | Its share of the overall score. The four weights sum to 100. |
| `components[].contribution` | Points it adds to `score`. The contributions sum to `score` (before rounding). |
| `components[].reason` | One sentence with the real counts behind the score. |

How each component is scored. The plan names the four components; **every
formula and weight below is an Assumption**, defined in one place
(`backend/insights/health.py`):

| Component | Weight | Score |
|---|---|---|
| Membership | 30 | 70% active share (people with a current membership, out of everyone who has ever joined) + 30% renewal rate (people who renewed, out of those whose membership ran out). If no membership has run out yet, the active share alone. |
| Attendance | 25 | Tickets checked in, out of tickets sold, across events with status `closed`. |
| Volunteering | 20 | Tasks done, out of all tasks. |
| Money | 25 | Of the cash that moved in the last 30 days, the share that was coming in. 50 means in equals out. |

A component with no data has `score: null` and is left out of the average, so
the remaining weights are scaled up.

Errors: `401`, `403 permission_denied`.

## GET /savefiles, POST /savefiles

Save Files: handover notes per event.

- **Who:** Event manager or president, for both reading and writing.

Save file object:

```json
{
  "id": 1,
  "event": { "id": 1, "title": "Freshers Night" },
  "vendors": "Sound: Beatbox Audio (reliable, book 3 weeks ahead).",
  "budget_notes": "Sound hire was the biggest cost.",
  "what_worked": "QR check-in kept the queue short.",
  "what_didnt": "Snacks ran out by 9 pm; order 20% more next time.",
  "checklist": ["Book venue", "Confirm sound vendor", "Open ticket sales"],
  "updated_at": "2026-10-10T18:30:00+05:30"
}
```

`GET /savefiles` returns a paginated list, most recently updated first.
`?event=<id>` returns that event's save file (zero or one result).

`POST /savefiles`:

| Field | Type | Required | Rules |
|---|---|---|---|
| `event` | integer | yes | An existing event. |
| `vendors`, `budget_notes`, `what_worked`, `what_didnt` | string | no | **Assumption:** at most 5000 characters each. |
| `checklist` | string[] | no | **Assumption:** a list of text items, at most 50, each at most 200 characters. |

- There is one save file per event. **Assumption** (the plan gives only GET
  and POST, and says save files are editable): POST for an event with no
  save file creates it (`201`); POST for an event that has one updates it
  (`200`).
- On update, only the fields sent are changed; send `""` or `[]` to clear one.
- Every create and every change writes an audit-log row (`savefile.created`,
  `savefile.updated` with the before and after of the changed fields).

Errors: `400 validation_error`, `401`, `403 permission_denied`.

---

## GET /audit

The audit log. Plan API table: "Audit, GET /audit, P".

- **Who:** President only.
- **Database:** read only. The log itself is append-only: no endpoint, and
  no database user, can edit or delete a row.

Newest first, 20 per page. Optional `?action=<name>` keeps only rows with
exactly that action (for example `?action=expense.approved`).

```json
{
  "count": 18,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 18,
      "actor": { "id": 4, "name": "Meera Nair" },
      "action": "savefile.created",
      "object_type": "insights.savefile",
      "object_id": 1,
      "before": null,
      "after": { "vendors": "Sound: Beatbox Audio", "checklist": ["Book venue"] },
      "at": "2026-10-10T21:10:03.120000+05:30"
    }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `actor` | object or `null` | `{ "id", "name" }` of who did it; `null` if not recorded. |
| `action` | string | One of: `role.assigned`, `stock.restocked`, `expense.approved`, `expense.rejected`, `expense.paid`, `savefile.created`, `savefile.updated`. |
| `object_type` | string | The kind of record, as `app.model`. |
| `object_id` | integer | Its id. |
| `before`, `after` | object or `null` | The changed values before and after. |
| `at` | timestamp | When it happened. |

Errors: `401`, `403 permission_denied`.
