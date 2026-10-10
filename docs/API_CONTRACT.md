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
- Lists are paginated (format to be agreed with the first list endpoint).
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
| 404 | `not_found` | The record does not exist. |
| 405 | `method_not_allowed` | Wrong HTTP method. |
| 415 | `unsupported_media_type` | The body is not JSON. |

Common per-field codes inside `errors`: `required`, `blank`, `invalid`,
`max_length`.

Known gap: a URL that matches no endpoint returns an HTML 404, not this shape.

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
| `membership_status` | string | `active`, `lapsed` or `none`. **Always `none` until memberships are built.** |

Use `roles` only to decide which menus to show. The server enforces every
permission regardless. Whether someone is a paid-up member comes from
`membership_status`, not from the `member` role.

---

## POST /auth/signup

Create an account and log in. Requirement: R1.

- **Who:** Public.
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

- **Who:** Public.
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
