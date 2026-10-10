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

Token authentication. Signup and login return a `token`; send it on every
other request:

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

Create an account and log in. Requirement: R1.

- **Who:** Public. Limited to 10 requests per minute per IP address
  (`429 throttled` beyond that).
- **Database:** creates one user and one token, together or not at all.

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

Response `201` (**Assumption:** signup returns a token so the new user is
logged in immediately):

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "user": {
    "id": 1,
    "email": "priya@example.com",
    "name": "Priya",
    "college_id": "SSA-001",
    "phone": "+919876543210",
    "roles": [],
    "membership_status": "none"
  }
}
```

Errors: `400 validation_error`. Extra per-field codes:

| Field | Code |
|---|---|
| `email` | `email_taken` |
| `password` | `password_too_short`, `password_too_common`, `password_entirely_numeric`, `password_too_similar` |

Password-strength errors are reported only after every field passes its basic
checks, so a first response may not list them.

## POST /auth/login

- **Who:** Public. Limited to 20 requests per minute per IP address
  (`429 throttled` beyond that).
- **Database:** creates the user's token if they have none.

Request:

```json
{ "email": "priya@example.com", "password": "correct-horse-battery" }
```

Response `200`: same body as signup (`token` and `user`).

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | `email` or `password` missing or malformed. |
| 401 | `invalid_credentials` | Wrong email, wrong password, or inactive account. The response is identical in all three cases. |

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
      { "id": 15, "kind": "membership", "plan": 1, "tier": null, "qty": 1, "unit_price": 50000 }
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
  "paid_until": "2027-10-10"
}
```

Errors: `401 not_authenticated`, `401 authentication_failed`.

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

Scan a ticket at the door. Requirements: R5, R9.

- **Who:** President or event manager only, because the answer reveals
  membership status.
- **Database:** for a valid, unused ticket: one check-in row (unique per
  ticket) and the ticket becomes `checked_in`.

Request: exactly one of `token` or `code`.

| Field | Type | Notes |
|---|---|---|
| `token` | string | The scanned QR content. |
| `code` | string | The short code typed by hand; case, spaces and dashes are ignored. |
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

Errors: `400 validation_error` (neither or both of `token` and `code`),
`401`, `403 permission_denied`.
