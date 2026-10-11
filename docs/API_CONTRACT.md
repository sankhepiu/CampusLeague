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

## Clubs

**Assumption:** the plan describes one club. Several clubs now share this
site. Each has its own database schema, with its own users, tokens, events,
shop, ledger and audit log; nothing is shared between them.

Every request may carry the club's slug:

```
X-Club: robotics
```

- **No header means `skyline`.** A client that never sends it behaves exactly
  as before.
- An unknown slug, or a club that has not been set up on this server, is
  `404` with `{ "code": "club_not_found", "message": "...", "field": null }`,
  on every endpoint.
- **A token belongs to one club.** Sent with another club's `X-Club` (or with
  none, when it is not a Skyline token) it is unknown: `401
  authentication_failed`. After login, send the `club.slug` from the login
  response as `X-Club` on every request.
- Ids are per club: event 3 in one club and event 3 in another are different
  events. Never reuse an id across clubs.
- The same email may have an account in several clubs. They are separate
  accounts (separate passwords, memberships and roles).

Club object:

```json
{ "slug": "robotics", "name": "Pixel Robotics Club", "short": "PRC", "color": "#4fd1c5" }
```

| Field | Notes |
|---|---|
| `slug` | The value for `X-Club`. |
| `name`, `short` | Full name and short label. |
| `color` | The club's accent colour, `#rrggbb`. |

### GET /clubs

- **Who:** Public. No token, and `X-Club` makes no difference.

Response `200`: an array (not paginated) of every club:

```json
[
  { "slug": "skyline", "name": "Skyline Student Association", "short": "SSA", "color": "#f5c542" },
  { "slug": "robotics", "name": "Pixel Robotics Club", "short": "PRC", "color": "#4fd1c5" },
  { "slug": "music", "name": "Raaga Music Society", "short": "RMS", "color": "#f472b6" }
]
```

### What changed for the frontend

Nothing breaks for a client that ignores clubs: without `X-Club` everything is
Skyline, as before. To support several clubs:

1. Login may now answer `409 choose_club` (see `POST /auth/login`). Show the
   listed clubs and log in again with `"club": "<slug>"`.
2. Keep `club` from the login response next to the token, and send
   `X-Club: <club.slug>` with every request.
3. `POST /auth/login`, `POST /auth/verify-email` and `GET /auth/me` responses
   have a new `club` key.
4. Signup, verify-email and resend-code act on the club in `X-Club`
   (default Skyline), so a signup page for another club must send the header.
5. Switching club means logging in to the other club: a different token.

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
  ],
  "fields": {
    "email": "An account with this email already exists.",
    "name": "This field may not be blank."
  }
}
```

`fields` holds the same problems keyed by field, one message each (the first
for that field), for forms that only need "what to show under which input".
Nested fields use dotted paths (`items.0.quantity`). A problem that belongs to
no single field is under the key `_`.

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
| 404 | `club_not_found` | The `X-Club` header (or login's `club`) names no club on this server. |
| 405 | `method_not_allowed` | Wrong HTTP method. |
| 415 | `unsupported_media_type` | The body is not JSON. |
| 429 | `throttled` | Too many requests. The `Retry-After` header gives the wait in seconds. |
| 500 | `server_error` | A bug on the server. The message is generic; details are only in the server log. |

Common per-field codes inside `errors`: `required`, `blank`, `invalid`,
`max_length`, `min_length`, `min_value`, `max_value`, `invalid_choice`,
`does_not_exist`.

### Validation limits

**Assumption:** the plan gives no limits; these are enforced on every write
endpoint and each has a test. A value outside them is a `400 validation_error`
on that field, and nothing is saved.

| What | Rule | Code when broken |
|---|---|---|
| Any amount of money (expense, sale, goal, budget, price, coupon value) | Whole paise, at most 1,000,000,000 (Rs 1 crore). Greater than zero, except `budget_amount` and a coupon's `min_order`, which may be 0. | `min_value`, `max_value`, `invalid` |
| Quantity in a purchase | 1 to 10 per ticket order and per merch item; at most 20 items in one merch order. | `min_value`, `max_value` |
| Restock quantity | 1 to 10,000. | `min_value`, `max_value` |
| Event times | `ends_at` after `starts_at`. A new event, or a changed `starts_at`, must be in the future. | `ends_before_start`, `starts_in_past` |
| Event capacity | 1 to 100,000, and never below what its tiers hold (which is never below what is sold). | `below_tier_capacity` |
| Tier capacity | At least 1 and within what the event has left. | `exceeds_event_capacity` |
| Tier sale window | `sale_closes` after `sale_opens`; `sale_closes` not after the event ends; `sale_opens` before the event ends. An event's `ends_at` cannot be moved before a tier's window. | `closes_before_opens`, `outside_event`, `before_sale_window` |
| Fundraiser dates | `ends_on` not before `starts_on`. | `ends_before_start` |
| Task due date | A due date being set or changed cannot be in the past. | `in_past` |
| Titles and names | Event title and venue, fundraiser title, task title, announcement title: 200. Product, tier and plan names: 100. Person's name: 2 to 150. | `max_length`, `min_length`, `blank` |
| Descriptions | Event, task and product description: 2,000. Expense description: 3 to 500. Notes: 200. | `max_length`, `min_length` |
| Announcement | `title` 3 to 200, `body` 3 to 5,000. | `max_length`, `min_length` |
| Email | A valid address, at most 254. | `invalid` |
| College id | 3 to 20 letters, digits or hyphens, starting and ending with a letter or digit (`SSA-001`, `CS21B1042`). | `invalid_college_id`, `max_length` |
| Receipt upload | `.png`, `.jpg`/`.jpeg` or `.pdf`; at most 5 MB; the declared content type must match the extension; the first bytes must be that file type's signature. | `unsupported_file_type`, `file_too_large`, `content_type_mismatch`, `file_content_mismatch` |
| Product sale | `sale_pct` 0 to 90. | `min_value`, `max_value` |
| Coupon | See "Coupons". | |

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
| `name` | string | yes | 2 to 150 characters. |
| `college_id` | string | yes | 3 to 20 letters, digits or hyphens, starting and ending with a letter or digit, for example `SSA-001` (`invalid_college_id`). **Changed:** it used to accept any text up to 50 characters. |
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

- **Clubs:** `X-Club` is not used here. With `"club"` in the body the login is
  for that club. Without it the email and password are tried in every club.

Request:

```json
{ "email": "priya@example.com", "password": "correct-horse-battery" }
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `email`, `password` | string | yes | |
| `club` | string | no | A club slug, any letter case. Needed only after a `choose_club` answer. |

Response `200`: `token`, `user` and **`club`** (new: the [club object](#clubs)
this token belongs to). `POST /auth/verify-email` returns the same three keys.

```json
{ "token": "9944b0...", "user": { "id": 7, "email": "priya@example.com", "...": "..." },
  "club": { "slug": "skyline", "name": "Skyline Student Association", "short": "SSA", "color": "#f5c542" } }
```

Response `409` when the email and password are right in more than one club.
No token is issued; ask the user which club and send the request again with
`"club"`:

```json
{
  "code": "choose_club",
  "message": "This account belongs to more than one club. Choose which one to open.",
  "field": null,
  "clubs": [
    { "slug": "skyline", "name": "Skyline Student Association", "short": "SSA", "color": "#f5c542" },
    { "slug": "robotics", "name": "Pixel Robotics Club", "short": "PRC", "color": "#4fd1c5" }
  ]
}
```

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | `email` or `password` missing or malformed. |
| 401 | `invalid_credentials` | Wrong email, wrong password, or inactive account. The response is identical in all three cases. |
| 403 | `email_not_verified` | The password is correct but the email has not been verified. Returned **only after the password matches**, so it reveals nothing to someone guessing. Send the user to the code screen. |
| 404 | `club_not_found` | `"club"` is not a club on this server. |
| 409 | `choose_club` | Valid in several clubs; see above. |

With `"club"` given, a password that is right in a different club is still
`401 invalid_credentials`.

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

Response `200`: a [user object](#user-object) plus **`club`** (new: the
[club object](#clubs) of the request's `X-Club`). `roles` and
`membership_status` are the user's in that club.

```json
{
  "id": 7,
  "email": "treasurer@example.com",
  "name": "Asha",
  "college_id": "SSA-010",
  "phone": "",
  "roles": ["treasurer"],
  "membership_status": "none",
  "club": { "slug": "skyline", "name": "Skyline Student Association", "short": "SSA", "color": "#f5c542" }
}
```

Errors: `401 not_authenticated`, `401 authentication_failed` (including a
token from another club), `404 club_not_found`.

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
| `coupon` | string | no | A coupon code. See "Coupons". |

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
    "coupon": null,
    "coupon_discount": 0,
    "total": 50000,
    "payment_ref": "mock_5b1f0c3e9a7d4e2f8c6b1a0d9e8f7a6b",
    "needs_refund": false,
    "created_at": "2026-10-10T11:42:07.123456+05:30",
    "lines": [
      { "id": 15, "kind": "membership", "label": "Basic membership", "plan": 1, "tier": null, "product_size": null, "qty": 1, "unit_price": 50000, "discount": 0, "coupon_discount": 0 }
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
| 400 | `coupon_invalid` | The coupon cannot be used for this purchase; `message` says why. Nothing was created. |
| 402 | `payment_failed` | `test_outcome: failure`. The order is cancelled; no payment, membership or ledger entry exists. |
| 409 | `idempotency_key_reused` | The key already paid for a different plan, or belongs to another user. |
| 409 | `coupon_limit_reached` | The coupon's last use went to someone else at the same moment. Nothing was created. |
| 409 | `gateway_not_enabled` | **New.** The server is on Razorpay, so this mock endpoint is closed (checked before anything else in the request). Use `POST /payments/razorpay/order`. The same applies to `POST /events/{id}/tickets` and `POST /orders`. |

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

- **Who:** President, treasurer, event manager or volunteer coordinator.
  Anyone else, including a paid-up member, gets `403 permission_denied`.
  **Assumption:** the plan lists president, treasurer and event manager; the
  volunteer coordinator is added because they assign people to tasks
  (`POST /tasks/{id}/assign`) and need the names to choose from.
- **Read-only:** the only method is `GET`. There is no way to create, edit
  or delete a member through this endpoint, for any role.
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

## Roles and role invites

Requirement: R19. **Assumption (changes the plan's direct assignment):** a role
is offered, not imposed. The president nominates someone; the role exists only
once that person accepts. Until then they have none of the role's access.

**Breaking change:** `POST /roles` used to create the role assignment and
return it. It now creates an invite and returns the invite object.

Role assignment object (unchanged): `{ "id", "user", "role", "term_start", "term_end", "created_at" }`,
where `user` is a user id.

Invite object:

```json
{
  "id": 7,
  "user": { "id": 11, "name": "Aditya Sharma", "email": "member05@skyline.test" },
  "role": "event_manager",
  "invited_by": { "id": 2, "name": "Ananya Rao" },
  "status": "pending",
  "term_start": "2026-10-11",
  "term_end": "2027-07-13",
  "expires_at": "2026-10-14T01:10:00+05:30",
  "created_at": "2026-10-11T01:10:00+05:30",
  "responded_at": null
}
```

| Field | Notes |
|---|---|
| `status` | `pending`, `accepted`, `declined`, `revoked` or `expired`. |
| `expires_at` | 72 hours after `created_at`. A pending invite past it is reported as `expired` and can no longer be accepted. |
| `term_start`, `term_end` | The term the role will have if accepted. |
| `responded_at` | When it was accepted, declined or revoked; otherwise `null`. |

### GET /roles

- **Who:** President only (`403 permission_denied` for everyone else,
  including a president whose term has ended or not yet started).

Response `200`: a paginated list of role assignment objects.

### POST /roles

Nominate someone for a role.

- **Who:** President only.
- **Database:** one invite and one audit-log row (`role.invited`), together or
  not at all. **No role assignment.**
- **Email:** the nominee is emailed (same mail settings as the verification
  code). If the email cannot be sent the invite still exists.

| Field | Type | Required | Rules |
|---|---|---|---|
| `user` | integer | yes | An active user whose email is verified. Anyone else is `does_not_exist`. |
| `role` | string | yes | `president`, `treasurer`, `event_manager`, `volunteer_coordinator` or `member`. |
| `term_start` | date | no | Default: today. |
| `term_end` | date | no | Default: one year after `term_start`. Not before `term_start` (`term_end_before_start`) and not already over (`term_in_past`). |

Response `201`: the invite object, `status` `pending`.

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | See the rules above. |
| 400 | `self_assignment` | `user` is the caller. |
| 401, 403 | | Not logged in; not a current president. |
| 409 | `invite_pending` | That person already has a pending invite for that role. |
| 409 | `role_already_held` | That person already holds that role for a term that has not ended. |

### GET /roles/invites

- **Who:** Any logged-in user. A president sees every invite; everyone else
  sees only invites addressed to them.
- Optional `?status=pending` (or any other status).

Response `200`: a paginated list of invite objects, newest first.

### POST /roles/invites/{id}/accept, /decline

- **Who:** The nominee only.
- **Database (accept):** in one transaction: the role assignment is created
  with the invite's term, the invite becomes `accepted`, and an audit-log row
  `role.assigned` is written (actor: the nominee; `after` names the invite and
  who sent it). If any part fails, none of it is saved.
- **Database (decline):** the invite becomes `declined`; audit row
  `role.invite_declined`. No role.

No body. Response `200`: the invite object.

| Status | `code` | When |
|---|---|---|
| 403 | `not_the_nominee` | A president, who can see the invite, tried to answer it. |
| 404 | `not_found` | No such invite, or one the caller cannot see. |
| 409 | `invite_not_pending` | Already accepted, declined, revoked, or expired. |

### POST /roles/invites/{id}/revoke

- **Who:** President only (`403 permission_denied` for the nominee; `404` for
  anyone who cannot see the invite).
- **Database:** the invite becomes `revoked`; audit row `role.invite_revoked`.

Response `200`: the invite object. `409 invite_not_pending` if it was already
answered or has expired.

### POST /roles/{id}/end

End a role assignment now.

- **Who:** President only.
- **Database:** the assignment's `term_end` becomes yesterday, so the access
  stops today; audit row `role.ended`. A term that started today is removed
  instead (a term cannot end before it starts). Nothing changes if the term
  was already over.
- **Rule:** the club always keeps at least one current president. The check
  locks the president rows, so two presidents cannot end each other at the
  same moment.

Response `200`: `{ "ended": true, "assignment": { ...role assignment } }`;
`assignment` is `null` when the row was removed.

| Status | `code` | When |
|---|---|---|
| 400 | `last_president` | This is the only current president. |
| 401, 403, 404 | | Not logged in; not a president; no such assignment. |

Treasurers still cannot approve, reject or pay their own expense
(`403 self_approval`); role invites do not change that.

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
| `sold` | integer | Seats sold in this tier. |
| `seats_left` | integer | For "X seats left". `0` means sold out. |
| `sale_opens`, `sale_closes` | timestamp or `null` | **Assumption:** `null` means no limit on that side. |
| `sale_open` | boolean | The event is `on_sale` and now is inside this tier's sale window. It says nothing about seats: a tier can be open and sold out, so check `seats_left` too. |

## GET /events, GET /events/{id}

Requirements: R6, R7, R8.

- **Who:** Public. Send the token when logged in so `price` reflects membership.
- **Database:** read only.

Response `200`: a paginated list of events, or one event.

`GET /events/{id}` returns the event object plus an overview (**Assumption:**
beyond the plan). The list does not include these fields.

| Field | Type | Notes |
|---|---|---|
| `organiser` | object | `{ "name" }`: whoever created the event. Events created before this was recorded show `Skyline Student Association`. |
| `capacity` | integer | Same value as `capacity_total`. |
| `sold` | integer | Seats sold across all tiers. |
| `seats_left` | integer | Seats still buyable: the sum of the tiers' `seats_left`. |
| `checked_in` | integer | People admitted so far. |
| `my_passes` | pass[] | The caller's own passes for this event (see "Pass object"); `[]` when not logged in. |
| `revenue` | integer | **President and event manager only**; absent for everyone else. Ticket revenue for this event from the ledger, paise. |
| `attendance_pct` | number or `null` | **President and event manager only.** `checked_in` as a percentage of `sold`, one decimal; `null` when nothing is sold. |

```json
{
  "id": 3, "title": "Board Games Meetup", "description": "Casual evening, snacks included.",
  "venue": "Student Centre, Room 2", "starts_at": "2026-10-21T01:10:00+05:30", "ends_at": "2026-10-21T04:10:00+05:30",
  "capacity_total": 25, "status": "on_sale",
  "tiers": [ { "id": 4, "name": "Entry", "public_price": 10000, "member_price": 5000, "price": 5000,
               "capacity": 25, "sold": 10, "seats_left": 15, "sale_opens": null, "sale_closes": null, "sale_open": true } ],
  "organiser": { "name": "Meera Nair" },
  "capacity": 25, "sold": 10, "seats_left": 15, "checked_in": 3,
  "my_passes": [],
  "revenue": 50000, "attendance_pct": 30.0
}
```

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
- **New rules:** a new event must start in the future, and an existing one
  cannot be moved into the past (`starts_in_past`); a past event can still be
  edited as long as `starts_at` is not changed. A tier's sale window must lie
  inside the event (`outside_event`), and the event's end cannot be moved
  before a tier's sale window (`before_sale_window`). Length and amount
  limits are in "Validation limits".
- The caller who creates an event is recorded as its organiser.

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
| `coupon` | string | no | A coupon code. See "Coupons". |

Responses: `201` (or `200` on a replay) with `order`, `payment`, `tickets` and
`pass`; `202` when pending (`tickets` is `[]`, `pass` is `null`, no seat is
held).

**New:** `pass` is the group pass for this purchase (see "Pass object"): one
QR code that admits everyone in the order. `tickets` is unchanged, and each
ticket's own `qr_token` still works at the door.

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
| 400 | `coupon_invalid` | The coupon cannot be used; `message` says why. |
| 409 | `coupon_limit_reached` | The coupon's last use went to someone else at the same moment. |
| 409 | `gateway_not_enabled` | The server is on Razorpay; this mock endpoint is closed. |

## Pass object

**Assumption (beyond the plan):** one QR code per ticket purchase. Buying N
tickets still creates N tickets (one per seat, so seat counting is unchanged)
and one pass that groups them. Each scan of the pass admits the next unused
ticket.

```json
{
  "pass_id": 12,
  "event": { "id": 3, "name": "Board Games Meetup", "title": "Board Games Meetup", "starts_at": "2026-10-21T01:10:00+05:30", "venue": "Student Centre, Room 2" },
  "tier": { "id": 4, "name": "Entry" },
  "quantity": 10,
  "admitted": 3,
  "remaining": 7,
  "qr_token": "eyJwIjoxMiwiZSI6M30:1vAbCd:Qm9...",
  "tickets": [ { "id": 70, "code": "K7MPQ2XD", "status": "checked_in" }, { "id": 71, "code": "H4TTW9BN", "status": "valid" } ],
  "created_at": "2026-10-11T01:10:00+05:30"
}
```

| Field | Notes |
|---|---|
| `pass_id` | Use it for `GET /tickets/passes/{id}`. |
| `event` | `name` and `title` are the same value (the event object calls it `title`). |
| `quantity` | Tickets on the pass. Cancelled tickets are not counted. |
| `admitted`, `remaining` | Tickets checked in so far, and those still unused. `admitted + remaining = quantity`. They are counted from the tickets, so they also reflect a ticket scanned on its own. |
| `qr_token` | Render as the QR code exactly as received. |
| `tickets` | The seats, oldest first: `status` is `valid`, `checked_in` or `cancelled`. `code` is the short code for typing in. |

Tickets bought before passes existed were each given a pass by a migration.

## GET /tickets/me

- **Who:** Any logged-in user. Only the caller's own passes, newest first.

**Breaking change:** this used to return ticket objects. It now returns a
paginated list of pass objects; the individual tickets are inside each pass.

## GET /tickets/passes/{id}

- **Who:** The pass's owner, or door staff (president, event manager,
  volunteer coordinator). Anyone else gets `404`, as for a pass that does not
  exist.

Response `200`: the pass object plus:

| Field | Notes |
|---|---|
| `order` | The order id. |
| `holder` | `{ "name" }` of the owner. |
| `history` | Check-ins, oldest first: `[{ "at": timestamp, "by": "Meera Nair", "count": 3 }]`. People admitted in one scan are one line. A ticket scanned on its own appears as a line with `count` 1. |

Errors: `401`, `404 not_found`.

## POST /checkin

Scan a ticket, or a member card, at the door. Requirements: R5, R9.

- **Who:** President, event manager or volunteer coordinator, because the
  answer reveals membership status. **Assumption:** the plan lists president
  and event manager only; the volunteer coordinator is added because they
  staff the door. Treasurer and ordinary members get `403`.
- **Database:** for a valid, unused ticket: one check-in row (unique per
  ticket) and the ticket becomes `checked_in`. A member card scan writes
  nothing. A pass scan does the same for each person admitted, with the
  pass and its tickets locked so two scanners cannot admit the same seat.

Request: exactly one of `token`, `code`, `member_token` or `pass_token`.

| Field | Type | Notes |
|---|---|---|
| `token` | string | The scanned QR content. |
| `code` | string | The short code typed by hand; case, spaces and dashes are ignored. |
| `member_token` | string | A member card's QR content (`member_qr_token` from `GET /memberships/me`). See "Member card" below. |
| `pass_token` | string | A group pass's QR content. A pass token sent as `token` is recognised too, so a scanner need not know which kind of code it read. See "Group pass" below. |
| `count` | integer | Group passes only. How many people to admit with this scan: 1 to 10, default 1. Ignored for tickets and member cards. |
| `event` | integer | Optional. **Assumption:** the event being scanned for; a ticket for any other event is `invalid`, a pass for any other event is `wrong_event`. |

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

### Group pass

When the token is a pass, the response (**always `200`**) has these keys:

```json
{
  "result": "admitted",
  "pass_id": 12,
  "admitted": 4,
  "admitted_now": 1,
  "total": 10,
  "remaining": 6,
  "holder": { "name": "Aarav Sharma" },
  "membership_status": "active",
  "event": { "id": 3, "name": "Board Games Meetup", "title": "Board Games Meetup" },
  "tier": { "id": 4, "name": "Entry" }
}
```

| `result` | Meaning | Fields |
|---|---|---|
| `admitted` | `admitted_now` people let in. | `admitted` is the running total including this scan; `remaining = total - admitted`. |
| `already_used` | Every ticket on the pass has been used. Admit nobody. | `admitted` equals `total`, `remaining` and `admitted_now` are `0`. |
| `wrong_event` | A genuine pass, but not for the `event` sent. | Everything else `null`. Nobody admitted. |
| `invalid` | Forged, altered or unknown. | The ticket response shape, with everything `null`. |

Asking for more than the pass has left is the one error:
`400 validation_error` on `count`, code `exceeds_remaining`, message
"Only N left on this pass."; nobody is admitted.

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
| `subtotal`, `discount`, `total` | integer | Paise. `total = subtotal - discount`, always. `discount` is every discount together: sale, member and coupon. |
| `coupon` | string or `null` | The coupon code used, or `null`. |
| `coupon_discount` | integer | The part of `discount` that came from the coupon; `0` without one. |
| `payment_ref` | string | Gateway reference (`mock_...` or Razorpay's `pay_...`); `""` until paid. Also set when `needs_refund` is true. |
| `needs_refund` | boolean | **Assumption.** `true` only on a `cancelled` Razorpay order whose buyer was charged but got nothing (sold out while paying). Always `false` for mock purchases. |
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
| `discount` | integer | Total discount on this line (sale, member and coupon). Paid = `qty * unit_price - discount`. |
| `coupon_discount` | integer | The part of `discount` that came from the order's coupon. |

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
| `category` | string | **New.** `apparel`, `accessories`, `stationery` or `drinkware`. |
| `base_price` | integer | Paise, before any discount. Show it struck through when it differs from `price`. |
| `sale_pct` | integer | **New.** 0 to 90: percent off for everyone. `0` means not on sale. |
| `price` | integer | What **the caller** would pay per item now: `base_price`, less the sale, less their plan's `merch_discount_pct` if their membership is active (in that order, each step rounded down). Display this one. A coupon is applied at checkout, after both. |
| `image_url` | string or `null` | Path of the product picture relative to the site root, `/media/products/<file>.png`, to load through the frontend's `/media` proxy; `null` when there is none. Replaces the earlier `image` field. **Assumption:** there is no upload endpoint; the seed provides the pictures. |
| `active` | boolean | Inactive products are returned to shop staff only. |
| `sizes` | array | `{ "id", "size", "stock" }`. Clothing has `S`, `M`, `L`, `XL` in that order. **New:** a product that does not come in sizes has exactly one entry, with `size` `ONE`, holding its stock; do not show a size picker for it. Use `id` when ordering either kind. |

## GET /products

Requirements: R13, R14.

- **Who:** Public. Send the token when logged in so `price` reflects membership.

Response `200`: a paginated list of product objects.

```json
{
  "id": 1, "name": "Skyline Hoodie", "description": "Heavyweight fleece with the club crest.",
  "category": "apparel", "base_price": 120000, "sale_pct": 0, "price": 96000,
  "image_url": "/media/products/skyline-hoodie.png", "active": true,
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
| `coupon` | string | no | A coupon code. See "Coupons". Its discount is shared across the lines in proportion to their cost. |

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
| 400 | `coupon_invalid` | The coupon cannot be used; `message` says why. |
| 409 | `coupon_limit_reached` | The coupon's last use went to someone else at the same moment. |
| 409 | `gateway_not_enabled` | The server is on Razorpay; this mock endpoint is closed. |

## GET /orders/me

- **Who:** Any logged-in user. The caller's own orders of every kind
  (membership, tickets, merch), newest first. Pending and cancelled orders
  are included; use `status` to tell them apart.

Response `200`: a paginated list of order objects. Each line's `label` says
what was bought, so no further lookups are needed:

```json
{
  "id": 121, "status": "paid", "subtotal": 160000, "discount": 32000, "coupon": null, "coupon_discount": 0, "total": 128000,
  "payment_ref": "mock_5b1f0c3e9a7d4e2f8c6b1a0d9e8f7a6b", "needs_refund": false, "created_at": "2026-10-10T18:20:00+05:30",
  "lines": [
    { "id": 140, "kind": "merch", "label": "Skyline Hoodie · M", "plan": null, "tier": null, "product_size": 2, "qty": 1, "unit_price": 120000, "discount": 24000, "coupon_discount": 0 },
    { "id": 141, "kind": "merch", "label": "Skyline T-Shirt · XL", "plan": null, "tier": null, "product_size": 8, "qty": 1, "unit_price": 40000, "discount": 8000, "coupon_discount": 0 }
  ]
}
```

## Coupons

**Assumption:** coupons are beyond the backend plan.

- **Price order:** sale price, then member discount, then the coupon, which is
  worked out on what is left after the first two.
- **Never free:** a coupon cannot take an order below 100 paise (Rs 1). Every
  order has a payment and a ledger entry, and neither can be zero.
- **Counting uses:** a use is counted only when the payment succeeds. A
  failed, pending or abandoned order uses nothing. The limits are enforced
  with the coupon row locked, so the last use cannot go to two buyers.
- **Ledger (Assumption):** unchanged. Revenue is posted at the amount actually
  paid, net of every discount, as before. The coupon and what it took off are
  stored on the order and its lines and shown by `GET /orders/me` and the
  trace. Reconciliation still runs the same 11 checks.

Coupon object:

| Field | Type | Notes |
|---|---|---|
| `id` | integer | |
| `code` | string | 3 to 20 letters, digits, `-` or `_`. Stored and returned in upper case; matching ignores case. Unique. |
| `kind` | string | `percent` or `flat`. |
| `value` | integer | For `percent`: 1 to 100. For `flat`: paise, 1 to 1,000,000,000. |
| `min_order` | integer | The purchase must cost at least this (after sale and member discounts). Default 0. |
| `max_discount` | integer or `null` | The most it can take off; `null` for no cap. |
| `valid_from`, `valid_to` | timestamp or `null` | `null` means no limit on that side. `valid_to` must be after `valid_from`. |
| `usage_limit` | integer or `null` | Paid orders in total; `null` for unlimited. Cannot be set below `used_count`. |
| `per_user_limit` | integer | Paid orders per user. Default 1. |
| `applies_to` | string | `all`, `merch`, `tickets` or `membership`. Default `all`. |
| `active` | boolean | Default `true`. |
| `used_count` | integer | Read-only: paid orders so far. |
| `created_at` | timestamp | |

Seeded: `WELCOME10` (10% off a membership), `GALA50` (Rs 50 off tickets, order
of Rs 200 or more), `MERCH20` (20% off merchandise, at most Rs 150, 5 uses).

### POST /coupons/validate

"What would this code take off?" Changes and reserves nothing; the purchase
checks the coupon again.

- **Who:** Any logged-in user.

Request (all required):

| Field | Type | Rules |
|---|---|---|
| `code` | string | Any letter case. |
| `applies_to` | string | `merch`, `tickets` or `membership`: what is being bought. |
| `amount` | integer | What the purchase costs before the coupon, in paise (for merch: the sum of `price * quantity`). |

Response: **always `200`**:

```json
{ "valid": true, "discount": 5000, "final_amount": 45000, "reason": null, "message": null }
```

When not valid, `discount` is `0`, `final_amount` equals `amount`, `message`
is text for the user, and `reason` is one of:

| `reason` | Meaning |
|---|---|
| `not_found` | No coupon has this code. |
| `inactive` | Switched off. |
| `not_started`, `expired` | Outside `valid_from` / `valid_to`. |
| `not_applicable` | Not for this kind of purchase. |
| `min_order_not_met` | `amount` is below `min_order`. |
| `usage_limit_reached` | Used up. |
| `already_used` | This user has reached `per_user_limit`. |
| `no_discount` | The purchase is too small for the coupon to take anything off. |

Errors: `400 validation_error` (a field missing, `applies_to` not one of the
three, `amount` out of range), `401`.

### Using a coupon

Send `"coupon": "CODE"` to `POST /memberships`, `POST /events/{id}/tickets`,
`POST /orders` or `POST /payments/razorpay/order`. An empty string or no field
means no coupon.

| Status | `code` | When |
|---|---|---|
| 400 | `coupon_invalid` | Any of the reasons above; `message` carries the text. Nothing is created. |
| 409 | `coupon_limit_reached` | Mock: the last use went to another buyer in the same instant; nothing is created. Razorpay verify: the coupon was used up while the buyer was paying; the order is flagged `needs_refund`, as for `sold_out`. |

### GET /coupons, POST /coupons, GET/PATCH/DELETE /coupons/{id}

- **Who:** President or treasurer.
- POST takes the coupon fields (`code`, `kind`, `value` required). PATCH
  accepts any subset. PUT is not supported. `used_count` cannot be set.
- DELETE removes a coupon that has never been on an order (`204`). One that
  has is refused with `409 coupon_in_use`; set `active` to `false` instead.

Responses: the coupon object (`201` on create), or a paginated list.
Errors: `400 validation_error` (codes include `unique`, `invalid`,
`invalid_choice`, `min_value`, `max_value`, `ends_before_start`,
`below_used_count`), `401`, `403 permission_denied`, `404 not_found`,
`409 coupon_in_use`.

## Razorpay payments

**Assumption:** everything in this section is beyond the backend plan, which
specifies only the mock gateway.

**Changed:** while the server is on Razorpay, the three mock purchase
endpoints (`POST /memberships`, `POST /events/{id}/tickets`, `POST /orders`)
refuse every request with `409 gateway_not_enabled`. They exist to give
things away for a test flag, so they are closed whenever a real gateway is
configured. With `PAYMENT_GATEWAY=mock` (or Razorpay keys missing) they work
as before. Use `GET /payments/config` to choose the flow.

The server picks the gateway with `PAYMENT_GATEWAY` (`mock`, the default, or
`razorpay`, test-mode keys). If `razorpay` is set but either key is empty, the
server uses `mock` and logs a warning.

A Razorpay purchase takes two requests, with Razorpay's checkout between them:

1. `POST /payments/razorpay/order`: the server validates and prices the
   purchase and returns what the checkout needs.
2. The browser opens Razorpay Checkout with those values. On success
   Razorpay gives the browser `razorpay_order_id`, `razorpay_payment_id` and
   `razorpay_signature`.
3. `POST /payments/razorpay/verify` with those three values: the server
   checks the signature and delivers the purchase.
4. If the buyer closes the checkout instead: `POST /payments/razorpay/cancel`.

Nothing is held between steps 1 and 3 (the same rule as the mock's `pending`
outcome), so seats or stock can run out while the buyer is paying. See
`sold_out` under verify.

**Not built (future work):** webhooks, which need a public URL. If the browser
never calls verify after a successful payment, the order stays `pending`.
Refunds are not automated: a `needs_refund` order is refunded by hand in the
Razorpay dashboard, using its `payment_ref`.

### GET /payments/config

- **Who:** Public (**changed:** it used to need a login). Call it on page
  load, before login; a token in the header is ignored. It returns only the
  two fields below, never the key secret.

Response `200`:

```json
{ "gateway": "razorpay", "key_id": "rzp_test_XXXXXXXXXXXXXX" }
```

| Field | Type | Notes |
|---|---|---|
| `gateway` | string | `mock` or `razorpay`: which purchase flow the frontend should use. |
| `key_id` | string or `null` | Optional for clients (the order response carries the key as `key`). Razorpay's public key id; `null` when `gateway` is `mock`. The key secret is never returned by any endpoint. |

Errors: none of its own (`404 club_not_found` for an unknown `X-Club`).

### POST /payments/razorpay/order

Start a checkout.

- **Who:** Any logged-in user. The buyer is the token's user.
- **Header:** `Idempotency-Key`, as for `POST /memberships`. Use a new key for
  every checkout attempt.
- **Validation and price:** the same code as the mock purchase of that purpose:
  sales window, seats, stock, product active, member ticket price, member
  merch discount. Any price or total in the body is ignored.
- **Database:** our order is saved as `pending` with its lines and the
  Razorpay order id. No payment, ticket, membership, stock change or ledger
  entry yet.

Request: `purpose`, plus the fields of the mock endpoint for that purpose.
`test_outcome` is ignored.

| `purpose` | Other fields |
|---|---|
| `membership` | `plan` (integer, required) |
| `tickets` | `tier` (integer, required), `quantity` (1 to 10, default 1), `event` (integer, optional; if sent it must be the tier's event) |
| `merch` | `items` (required), exactly as in `POST /orders` |

Every purpose also takes an optional `coupon` (see "Coupons"). `amount` in the
response is then the discounted total.

```json
{ "purpose": "tickets", "event": 3, "tier": 7, "quantity": 2 }
```

Response `201` (or `200` when the same key already started this same
checkout and it is still open; nothing new is created):

```json
{
  "order_id": 131,
  "razorpay_order_id": "order_QxT3lB0nH1kP9a",
  "key": "rzp_test_XXXXXXXXXXXXXX",
  "amount": 160000,
  "currency": "INR",
  "name": "Skyline Student Association",
  "description": "Spring Gala · General x2",
  "prefill": { "name": "Priya Nair", "email": "priya@example.com" }
}
```

`name` is the name of the club in `X-Club` (before clubs it was always
Skyline's). `key` is Razorpay's public key id (the same value as `key_id` in
`GET /payments/config`), named as Razorpay Checkout expects it. `amount` is
in paise and is what Razorpay will charge. `description` is the
order's line labels (with ` x<qty>` for tickets and merch), comma separated.

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `idempotency_key_required` | Header missing or malformed. |
| 400 | `validation_error` | Missing or unknown `purpose`; missing or unknown `plan`; `tier` missing, unknown, in a draft event, or not in `event`; bad `items`. |
| 400 | `amount_too_small` | Total under 100 paise, Razorpay's minimum. |
| 409 | `sales_closed`, `sold_out` | Tickets, as for `POST /events/{id}/tickets`. |
| 409 | `out_of_stock`, `product_unavailable` | Merch, as for `POST /orders`. |
| 400 | `coupon_invalid` | The coupon cannot be used; no checkout is started. |
| 409 | `idempotency_key_reused` | The key belongs to another user, a different purchase, a mock payment, or a checkout that is already paid or cancelled. |
| 409 | `gateway_not_enabled` | The server is on the mock gateway. Use the mock endpoints. |
| 502 | `gateway_unavailable` | Razorpay could not be reached or refused the request. Nobody was charged; the order is cancelled and the same key may be sent again. |

### POST /payments/razorpay/verify

Prove the payment and deliver the purchase.

- **Who:** The buyer of the order only. Anyone else gets `404`, the same as
  for an order that does not exist.
- **Signature:** the server computes HMAC-SHA256 of
  `razorpay_order_id + "|" + razorpay_payment_id` with the key secret, using
  the Razorpay order id it stored in step 1, and compares in constant time.
- **Database:** on a match, the same success path as the mock, in one
  transaction: payment (`gateway_ref` = `razorpay_payment_id`), order `paid`,
  then membership, or tickets and seats, or stock and stock movements, and the
  ledger entry. If any part fails, none of it is saved.

Request (all required):

```json
{
  "order_id": 131,
  "razorpay_order_id": "order_QxT3lB0nH1kP9a",
  "razorpay_payment_id": "pay_QxT4w2e8ZrUu1c",
  "razorpay_signature": "9f6c...64 hex characters...b1"
}
```

Response `201`: exactly the body of the mock endpoint for that purpose
(`{order, payment, membership}`, `{order, payment, tickets, pass}` or
`{order, payment}`), with `order.status` `paid`. Sending the same payment
again returns `200` with the same body and creates nothing.

**Assumption:** a genuine payment for an order the buyer has already
cancelled (the two calls can race when the checkout closes) is still
delivered, since Razorpay has the money.

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | A field is missing. |
| 400 | `invalid_signature` | The signature does not match, or `razorpay_order_id` is not this order's. Nothing changes; the order stays as it was and can still be verified with the right values. |
| 404 | `not_found` | No such order, another user's order, or an order that was not started through Razorpay. |
| 409 | `sold_out` | The seats or stock (any one line) were gone by the time the payment arrived. Nothing is delivered; the order becomes `cancelled` with `needs_refund: true` and `payment_ref` set, and an audit row `order.refund_due` is written. Repeating the call gives the same `409`. Used for merch too (not `out_of_stock`). |
| 409 | `coupon_limit_reached` | The order's coupon was used up by other buyers while this one was paying. Handled like `sold_out`: nothing delivered, `needs_refund: true`, audit row `order.refund_due` (its `after.reason` says which). |
| 409 | `order_already_paid` | The order was already paid by a different payment id. |
| 409 | `gateway_not_enabled` | The server is on the mock gateway. |

### POST /payments/razorpay/cancel

The buyer closed the checkout without paying.

- **Who:** The buyer of the order only (`404` otherwise).
- **Database:** the order goes from `pending` to `cancelled`. Nothing else
  changes. Calling it again returns the same `200`.

Request: `{ "order_id": 131 }`

Response `200`: `{ "order": { ...order object, "status": "cancelled" } }`

Errors:

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | `order_id` missing. |
| 404 | `not_found` | No such order, another user's, or not a Razorpay order. |
| 409 | `order_already_paid` | The order is `paid`; it stays paid. Safe to ignore if the checkout's close event fires after a successful verify. |
| 409 | `gateway_not_enabled` | The server is on the mock gateway. |

## POST /products, PATCH /products/{id}, POST /products/{id}/restock

- **Who:** President, treasurer or event manager.
- **Product fields:** `name` (unique ignoring case, max 100), `base_price`
  (required on create); `description`, `active`, `category` (default
  `apparel`), `sale_pct` (0 to 90, default 0). PATCH accepts any subset. The
  picture and stock cannot be set here.
- **Sizes:** on create only, `sized` (boolean, default `true`).
  **Assumption:** a sized product gets `S`, `M`, `L`, `XL`; with
  `"sized": false` it gets the single size `ONE`. All start at zero stock,
  and a product's sizes cannot be changed afterwards.
- **Restock:** `{ "size": "M", "quantity": 7 }` (`"size": "ONE"` for a product
  without sizes), quantity 1 to 10000. Adds to stock, writes a stock movement
  and an audit-log row (`stock.restocked`). A size the product does not have
  is `404`.

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

Request: `title` (3 to 200 characters), `body` (3 to 5,000), optional `audience`
(`all`, the default, or `members`).
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
- **Amount and description:** `amount` 1 to 1,000,000,000 paise;
  `description` 3 to 500 characters.
- **Receipt:** JPG, PNG or PDF, at most 5 MB. Three things are checked: the
  file name's extension, the content type the upload declares (`image/png`,
  `image/jpeg`, `application/pdf`; **new**), and the file's first bytes. Codes
  on `receipt_file`: `required`, `unsupported_file_type`, `file_too_large`,
  `content_type_mismatch`, `file_content_mismatch`.
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
| `payment` | Membership dues | `order`, `member`, `plan`, `membership`, `amount` (paid), `list_price`, `discount`, `coupon` (code or `null`), `coupon_discount` |
| `order_line` | Tickets | `order`, `buyer`, `tickets` (each: `type`, `id`, `code`, `holder`, `price_paid`, `status`, `checked_in_at`), `list_price`, `discount`, `paid`, `coupon`, `coupon_discount` |
| `order` | Merchandise | `order` (the order id, same as `source.id`), `buyer`, `items` (each: `product`, `size`, `qty`, `unit_price`, `discount`, `coupon_discount`, `paid`), `discount`, `coupon`, `coupon_discount` |
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

Rules (see "Validation limits"): `goal_amount` and a sale's `amount` are 1 to
1,000,000,000 paise; `ends_on` not before `starts_on` (`ends_before_start`);
a task's `due_date`, when set or changed, cannot be in the past (`in_past`);
a task belongs to exactly one fundraiser or event (`one_parent_required`).

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
| `action` | string | One of: `role.invited`, `role.assigned`, `role.invite_declined`, `role.invite_revoked`, `role.ended`, `stock.restocked`, `order.refund_due`, `expense.approved`, `expense.rejected`, `expense.paid`, `savefile.created`, `savefile.updated`. |
| `object_type` | string | The kind of record, as `app.model`. |
| `object_id` | integer | Its id. |
| `before`, `after` | object or `null` | The changed values before and after. |
| `at` | timestamp | When it happened. |

Errors: `401`, `403 permission_denied`.
