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
      { "id": 15, "kind": "membership", "plan": 1, "tier": null, "product_size": null, "qty": 1, "unit_price": 50000, "discount": 0 }
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
| `plan`, `tier`, `product_size` | integer or `null` | The one matching `kind` is set. |
| `qty` | integer | |
| `unit_price` | integer | Per unit, before discount. |
| `discount` | integer | Total discount on this line. Paid = `qty * unit_price - discount`. |

## Product object

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `name`, `description` | string | |
| `base_price` | integer | Paise, before member discount. |
| `price` | integer | What **the caller** would pay per item now (their plan's `merch_discount_pct` applied if their membership is active). Display this one. |
| `image` | string | **Assumption:** a URL; `""` if none. No upload endpoint. |
| `active` | boolean | Inactive products are returned to shop staff only. |
| `sizes` | array | Always `S`, `M`, `L`, `XL` in that order: `{ "id", "size", "stock" }`. Use `id` when ordering. |

## GET /products

Requirements: R13, R14.

- **Who:** Public. Send the token when logged in so `price` reflects membership.

Response `200`: a paginated list of product objects.

```json
{
  "id": 1, "name": "Skyline Hoodie", "description": "Heavyweight fleece with the club crest.",
  "base_price": 120000, "price": 96000, "image": "", "active": true,
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
  (membership, tickets, merch), newest first.

Response `200`: a paginated list of order objects.

## POST /products, PATCH /products/{id}, POST /products/{id}/restock

- **Who:** President, treasurer or event manager.
- **Product fields:** `name` (unique), `base_price` (required on create);
  `description`, `image`, `active`. PATCH accepts any subset. Stock cannot be
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
| `receipt_url` | string | Absolute URL of the uploaded receipt. |
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
      "lines": [ { "id": 88, "account": { "code": "4100", "name": "Ticket revenue" }, "debit": 0, "credit": 30000 } ],
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
- `entries` is newest first and capped at 200; `entry_count` is the full count.
- `source.type` is `payment` (dues), `order_line` (tickets, with each ticket
  and its `checked_in_at`), `order` (merch, with items), `expense_request`
  (with `receipt_url` and `approved_by`) or `fundraiser_sale`.

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
