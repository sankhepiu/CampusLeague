"""Issuing tickets, signing QR tokens, and checking tickets in."""
import secrets
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from finance.models import LedgerEntry
from finance.services import post_entry
from members.services import membership_status

from .models import CheckIn, Ticket, TicketTier

User = get_user_model()

CASH = '1000'
TICKET_REVENUE = '4100'

# No 0/O or 1/I/L, so a code read aloud or typed by hand is unambiguous.
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 8

# Separates ticket tokens from anything else signed with the same secret.
QR_SALT = 'campusleague.ticket-qr'


class SoldOut(Exception):
    """Not enough seats left in the tier."""


# QR tokens ---------------------------------------------------------------

def sign_ticket(ticket_id, event_id):
    """Plan: "a signed token that contains the ticket id and event id plus a
    signature made with a server secret."

    django.core.signing appends an HMAC-SHA256 signature keyed with
    SECRET_KEY, which is read from the environment and never stored in the
    repo. The payload is readable by anyone (it is only base64), but it
    cannot be changed or invented without the key.
    """
    return signing.dumps({'t': ticket_id, 'e': event_id}, salt=QR_SALT)


def read_token(token):
    """Return (ticket_id, event_id), or None if the signature is wrong."""
    try:
        payload = signing.loads(token, salt=QR_SALT)
        return int(payload['t']), int(payload['e'])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


# Member cards ------------------------------------------------------------

# A different salt from tickets: a ticket token can never be replayed as a
# member token, or the other way round, even though both use the same secret.
MEMBER_QR_SALT = 'campusleague.member-qr'


def sign_member(user_id):
    """Plan, "Membership card QR. Optional but useful: a signed token for the
    member, so the door can scan a member card and show active or lapsed
    status." Same mechanism as sign_ticket; contains only the user id.
    """
    return signing.dumps({'u': user_id}, salt=MEMBER_QR_SALT)


def read_member_token(token):
    """Return the user id, or None if the signature is wrong."""
    try:
        return int(signing.loads(token, salt=MEMBER_QR_SALT)['u'])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def scan_member(token):
    """Look up a member card. Reads only: no CheckIn row, no ticket change.
    Returns (result, user or None, membership status or None).
    """
    user_id = read_member_token(token)
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id is not None else None
    if user is None:
        return 'invalid', None, None
    status = membership_status(user)
    return ('member_ok' if status == 'active' else 'not_member'), user, status


def new_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


# Issuing -----------------------------------------------------------------

def issue_tickets(line, payment):
    """Take the seats for a paid ticket line, create its tickets and post
    the ledger entry. Runs inside the purchase transaction, which already
    holds a row lock on the tier.
    """
    order = line.order
    tier = line.tier
    # Conditional update: the WHERE clause re-checks capacity in the same
    # statement that takes the seats, so this is safe even if a caller
    # forgot the lock. No row updated means the seats were not there.
    taken = TicketTier.objects.filter(
        pk=tier.pk, sold_count__lte=F('capacity') - line.qty,
    ).update(sold_count=F('sold_count') + line.qty, updated_at=timezone.now())
    if not taken:
        raise SoldOut()

    tickets = []
    for _ in range(line.qty):
        ticket = Ticket.objects.create(
            event_id=tier.event_id, tier=tier, owner=order.buyer, order=order,
            code=new_code(), qr_token='', price_paid=line.amount // line.qty,
        )
        # The token contains the ticket id, which exists only after insert.
        ticket.qr_token = sign_ticket(ticket.pk, tier.event_id)
        ticket.save(update_fields=['qr_token'])
        tickets.append(ticket)

    # Plan posting rule: ticket order paid -> debit Cash, credit Ticket
    # revenue (tagged with the event), one entry per ticket order line.
    post_entry(
        description=f'Tickets: {tier.event.title} / {tier.name} x{line.qty}',
        source_type=LedgerEntry.SourceType.ORDER_LINE,
        source_id=line.pk,
        kind=LedgerEntry.Kind.TICKET_SALE,
        event=tier.event,
        created_by=order.buyer,
        lines=[(CASH, line.amount, 0), (TICKET_REVENUE, 0, line.amount)],
    )
    return tickets


# Check-in ----------------------------------------------------------------

@dataclass
class ScanResult:
    # ok, already_checked_in, invalid or cancelled (the plan's four values).
    result: str
    ticket: Ticket | None = None
    checkin: CheckIn | None = None
    membership_status: str | None = None


def _find_ticket(token, code, event_id):
    if token:
        ids = read_token(token)
        if ids is None:
            return None
        ticket_id, token_event_id = ids
        ticket = Ticket.objects.filter(pk=ticket_id).first()
        # "Validation checks the signature and then the ticket row."
        if ticket is None or ticket.event_id != token_event_id or ticket.qr_token != token:
            return None
    else:
        normalised = code.strip().upper().replace('-', '').replace(' ', '')
        ticket = Ticket.objects.filter(code=normalised).first()
        if ticket is None:
            return None
    if event_id is not None and ticket.event_id != event_id:
        return None  # a real ticket, but for a different event
    return ticket


def scan(*, operator, token='', code='', event_id=None):
    """Check a ticket in. Exactly one CheckIn row can ever exist per ticket.

    Returns the same answer however many times, and however quickly, the
    same ticket is scanned: the first scan is "ok", every later one is
    "already_checked_in" with the original time and operator.
    """
    found = _find_ticket(token, code, event_id)
    if found is None:
        return ScanResult('invalid')

    try:
        with transaction.atomic():
            # Row lock: a second scan of the same ticket waits here until
            # the first has committed, then sees its CheckIn row.
            ticket = (
                Ticket.objects.select_for_update(of=('self',))
                .select_related('owner', 'event', 'tier').get(pk=found.pk)
            )
            existing = CheckIn.objects.select_related('scanned_by').filter(ticket=ticket).first()
            if existing:
                return ScanResult('already_checked_in', ticket, existing, existing.member_status_at_scan)
            status = membership_status(ticket.owner)
            if ticket.status == Ticket.Status.CANCELLED:
                return ScanResult('cancelled', ticket, None, status)

            checkin = CheckIn.objects.create(
                ticket=ticket, scanned_by=operator, scanned_at=timezone.now(),
                member_status_at_scan=status,
            )
            ticket.status = Ticket.Status.CHECKED_IN
            ticket.save(update_fields=['status', 'updated_at'])
            return ScanResult('ok', ticket, checkin, status)
    except IntegrityError:
        # The UNIQUE constraint on CheckIn.ticket fired: another scan won
        # despite the lock. Report the winner's check-in.
        ticket = Ticket.objects.select_related('owner', 'event', 'tier').get(pk=found.pk)
        existing = CheckIn.objects.select_related('scanned_by').get(ticket=ticket)
        return ScanResult('already_checked_in', ticket, existing, existing.member_status_at_scan)
