#!/usr/bin/env bash
# Campus League: integrity walkthrough over real HTTP.
#
# Shows, with the actual status code of every request, the rules the backend
# enforces: server-side pricing, idempotent payments, role checks, signed QR
# tokens, single check-in, stock that cannot go negative, no self-approval,
# and a ledger that reconciles and can be traced.
#
# Run it on a FRESH seed (it buys the last hoodie XL, uses up a ticket and
# accepts the pending role invite):
#
#     python manage.py seed_demo --reset
#     PAYMENT_GATEWAY=mock python manage.py runserver     # in another terminal
#     scripts/demo.sh
#
# The server must be on the mock gateway: with Razorpay configured the
# purchase steps are refused (409 gateway_not_enabled), as they should be.
#
# Options (environment variables):
#     BASE           where the API is; default http://127.0.0.1:8000
#     DEMO_PASSWORD  the seed's password; default skyline-demo-2026
#
# Exits non-zero if any step returns a different status than expected.
set -uo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
API="$BASE/api"
PASSWORD="${DEMO_PASSWORD:-skyline-demo-2026}"
RUN="$(date +%s)"                 # makes this run's idempotency keys unique
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
FAILED=0
STEP=0
STATUS=""
BODY=""

# request METHOD PATH [TOKEN] [JSON_BODY] [IDEMPOTENCY_KEY]  -> sets STATUS, BODY
request() {
    local args=(-s -o "$TMP" -w '%{http_code}' -X "$1" "$API$2" -H 'Content-Type: application/json')
    [ -n "${3:-}" ] && args+=(-H "Authorization: Token $3")
    [ -n "${4:-}" ] && args+=(-d "$4")
    [ -n "${5:-}" ] && args+=(-H "Idempotency-Key: $5")
    STATUS="$(curl "${args[@]}")"
    BODY="$(cat "$TMP")"
}

# field 'python expression over d'  -> prints the value from the last BODY
field() {
    printf '%s' "$BODY" | python3 -c 'import sys, json; d = json.load(sys.stdin); print(eval(sys.argv[1]))' "$1"
}

# step EXPECTED_STATUS "caption" 'python expression for the detail line'
step() {
    STEP=$((STEP + 1))
    local mark="ok"
    if [ "$STATUS" != "$1" ]; then mark="UNEXPECTED (wanted $1)"; FAILED=1; fi
    printf '\n%2d. %s\n    HTTP %s  %s\n' "$STEP" "$2" "$STATUS" "$mark"
    if [ -n "${3:-}" ]; then printf '    %s\n' "$(field "$3")"; fi
}

login() {
    request POST /auth/login "" "{\"email\":\"$1@skyline.test\",\"password\":\"$PASSWORD\"}"
    if [ "$STATUS" != "200" ]; then
        echo "Could not log in as $1@skyline.test (HTTP $STATUS). Is the server running at $BASE on a fresh seed?" >&2
        exit 2
    fi
    field "d['token']"
}

echo "Campus League integrity walkthrough against $API"

MEMBER="$(login member10)" || exit 2
DOOR="$(login events)" || exit 2
TREASURER="$(login treasurer)" || exit 2

request GET /events "$MEMBER"
GALA="$(field "[e['id'] for e in d['results'] if e['title'] == 'Spring Gala'][0]")"
TIER="$(field "[t['id'] for e in d['results'] if e['title'] == 'Spring Gala' for t in e['tiers'] if t['name'] == 'General'][0]")"
MEMBER_PRICE="$(field "[t['member_price'] for e in d['results'] if e['title'] == 'Spring Gala' for t in e['tiers'] if t['name'] == 'General'][0]")"

echo
echo "== Tickets: the server sets the price, and a retry never charges twice =="

request POST "/events/$GALA/tickets" "$MEMBER" "{\"tier\":$TIER,\"price\":1,\"total\":1}" "demo-ticket-$RUN"
step 201 "Member buys a Spring Gala ticket; the request claims price=1" \
    "'charged %s paise (member price is $MEMBER_PRICE), order %s, ticket %s' % (d['order']['total'], d['order']['status'], d['tickets'][0]['code'])"
TICKET_CODE="$(field "d['tickets'][0]['code']")"
QR="$(field "d['tickets'][0]['qr_token']")"

request POST "/events/$GALA/tickets" "$MEMBER" "{\"tier\":$TIER}" "demo-ticket-$RUN"
step 200 "The same request again (double click, same Idempotency-Key)" \
    "'same ticket returned: %s (first was $TICKET_CODE); nothing new charged' % d['tickets'][0]['code']"

echo
echo "== Door: roles, forged codes, and one check-in per ticket =="

request POST /checkin "$MEMBER" "{\"token\":\"$QR\"}"
step 403 "The member tries to check their own ticket in" "'refused: ' + d['code']"

request POST /checkin "$DOOR" "{\"token\":\"${QR%?}x\"}"
step 200 "Event manager scans a tampered QR token" "'result: ' + d['result']"

request POST /checkin "$DOOR" "{\"token\":\"$QR\"}"
step 200 "Event manager scans the real ticket" \
    "'result: %s, holder %s, membership %s' % (d['result'], d['holder_name'], d['membership_status'])"
FIRST_SCAN="$(field "d['checked_in_at']")"

request POST /checkin "$DOOR" "{\"token\":\"$QR\"}"
step 200 "The same ticket is scanned a second time" \
    "'result: %s, original scan %s by %s (kept: %s)' % (d['result'], d['checked_in_at'], d['checked_in_by'], d['checked_in_at'] == '$FIRST_SCAN')"

echo
echo "== Group pass: one QR code for ten people, used up seat by seat =="

GROUP="$(login member01)" || exit 2
request GET /tickets/me "$GROUP"
PASS_QR="$(field "[p['qr_token'] for p in d['results'] if p['quantity'] == 10][0]")"
step 200 "member01's passes: one booking of ten for the Board Games Meetup" \
    "'%s: %d tickets, %d admitted, %d remaining, one QR code' % ([p['event']['name'] for p in d['results'] if p['quantity'] == 10][0], [p['quantity'] for p in d['results'] if p['quantity'] == 10][0], [p['admitted'] for p in d['results'] if p['quantity'] == 10][0], [p['remaining'] for p in d['results'] if p['quantity'] == 10][0])"

request POST /checkin "$DOOR" "{\"token\":\"$PASS_QR\",\"count\":2}"
step 200 "Event manager scans the pass for two more of the group" \
    "'result: %s, %d of %d inside, %d remaining' % (d['result'], d['admitted'], d['total'], d['remaining'])"

request POST /checkin "$DOOR" "{\"token\":\"$PASS_QR\",\"count\":6}"
step 400 "The scanner asks to admit six, but only five are left" "'%s: %s' % (d['code'], d['message'])"

echo
echo "== Coupons: checked on the server, never below one rupee =="

request POST /coupons/validate "$MEMBER" '{"code":"welcome10","applies_to":"membership","amount":50000}'
step 200 "Member asks what WELCOME10 takes off a Rs 500 membership" \
    "'valid: %s, discount %s paise, to pay %s paise' % (d['valid'], d['discount'], d['final_amount'])"

request POST /coupons/validate "$MEMBER" '{"code":"WELCOME10","applies_to":"tickets","amount":50000}'
step 200 "The same code on tickets" "'valid: %s (%s)' % (d['valid'], d['reason'])"

request POST "/events/$GALA/tickets" "$MEMBER" "{\"tier\":$TIER,\"coupon\":\"GALA50\"}" "demo-coupon-$RUN"
step 201 "Member buys another Gala ticket with GALA50 (Rs 50 off)" \
    "'list %s, coupon %s took off %s, charged %s paise' % (d['order']['subtotal'], d['order']['coupon'], d['order']['coupon_discount'], d['order']['total'])"

echo
echo "== Roles: a nomination grants nothing until the nominee accepts =="

NOMINEE="$(login member05)" || exit 2
request POST /events "$NOMINEE" '{}'
step 403 "member05, nominated as event manager, tries to create an event" "'refused: ' + d['code']"

request GET "/roles/invites?status=pending" "$NOMINEE"
INVITE="$(field "d['results'][0]['id']")"
request POST "/roles/invites/$INVITE/accept" "$TREASURER"
step 404 "The treasurer tries to accept member05's invite" "'refused: ' + d['code']"

request POST "/roles/invites/$INVITE/accept" "$NOMINEE"
step 200 "member05 accepts their own invite" \
    "'invite %s as %s, invited by %s' % (d['status'], d['role'], d['invited_by']['name'])"

request POST /events "$NOMINEE" '{}'
step 400 "member05 tries again: now allowed in, and told what is missing" "'%s: %s' % (d['code'], ', '.join(sorted(d['fields'])))"

echo
echo "== Shop: stock is taken atomically and stops at zero =="

request GET /products "$MEMBER"
XL="$(field "[s['id'] for p in d['results'] if p['name'] == 'Skyline Hoodie' for s in p['sizes'] if s['size'] == 'XL'][0]")"
XL_STOCK="$(field "[s['stock'] for p in d['results'] if p['name'] == 'Skyline Hoodie' for s in p['sizes'] if s['size'] == 'XL'][0]")"

request POST /orders "$MEMBER" "{\"items\":[{\"product_size\":$XL,\"quantity\":1}]}" "demo-hoodie-a-$RUN"
step 201 "Member buys the last Skyline Hoodie XL (stock was $XL_STOCK)" \
    "'order %s, paid %s paise after %s discount' % (d['order']['status'], d['order']['total'], d['order']['discount'])"

request POST /orders "$MEMBER" "{\"items\":[{\"product_size\":$XL,\"quantity\":1}]}" "demo-hoodie-b-$RUN"
step 409 "Member tries to buy another one" "'%s: %s' % (d['code'], d['message'])"

echo
echo "== Reimbursements: nobody approves their own request =="

request GET /expenses/me "$TREASURER"
OWN="$(field "[e['id'] for e in d['results'] if e['status'] == 'submitted'][0]")"
request POST "/expenses/$OWN/approve" "$TREASURER"
step 403 "The treasurer tries to approve the treasurer's own expense #$OWN" "'refused: %s (%s)' % (d['code'], d['message'])"

echo
echo "== Ledger: it reconciles, and every figure can be traced =="

request GET /finance/reconcile "$TREASURER"
step 200 "Reconciliation: ledger totals against the source records" \
    "'all pass: %s (%d of %d checks)' % (d['ok'], sum(c['ok'] for c in d['checks']), len(d['checks']))"

request GET /events "$TREASURER"
FRESHERS="$(field "[e['id'] for e in d['results'] if e['title'] == 'Freshers Night'][0]")"
request GET "/finance/trace?figure=event:$FRESHERS:profit" "$TREASURER"
step 200 "Coin Trail: where the Freshers Night profit comes from" \
    "'profit %s paise from %d ledger entries; every entry balances: %s; sum of entries equals total: %s' % (d['total'], d['entry_count'], all(sum(l['debit'] for l in e['lines']) == sum(l['credit'] for l in e['lines']) for e in d['entries']), sum(e['amount'] for e in d['entries']) == d['total'])"

echo
if [ "$FAILED" -eq 0 ]; then
    echo "All $STEP steps returned the expected status."
else
    echo "One or more steps returned an unexpected status." >&2
fi
exit "$FAILED"
