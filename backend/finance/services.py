from django.db import transaction
from django.db.models import Sum

from .models import LedgerAccount, LedgerEntry, LedgerLine


class LedgerError(ValueError):
    """The requested entry is not a valid double-entry posting."""


def _amount(value):
    # bool is a subclass of int in Python, so it is excluded explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(f'Amounts must be whole paise (int), got {value!r}.')
    if value < 0:
        raise LedgerError(f'Amounts cannot be negative, got {value}.')
    return value


@transaction.atomic
def post_entry(*, description, source_type, source_id, kind, lines, event=None, created_by=None, reverses=None):
    """Create one balanced ledger entry. The only way entries are written.

    lines is a list of (account_code, debit, credit) in paise, for example
    [('1000', 50000, 0), ('4000', 0, 50000)].

    Raises LedgerError if the lines do not form a balanced entry, and
    IntegrityError if this (source_type, source_id, kind) was already posted.
    Runs inside the caller's transaction, so the caller's change and its
    ledger entry are saved together or not at all.
    """
    if len(lines) < 2:
        raise LedgerError('An entry needs at least two lines.')

    total_debit = total_credit = 0
    for code, debit, credit in lines:
        debit, credit = _amount(debit), _amount(credit)
        if (debit > 0) == (credit > 0):
            raise LedgerError(f'Line for {code} must have exactly one of debit or credit.')
        total_debit += debit
        total_credit += credit
    if total_debit != total_credit:
        raise LedgerError(f'Entry does not balance: debits {total_debit}, credits {total_credit}.')

    codes = {code for code, _, _ in lines}
    accounts = {account.code: account for account in LedgerAccount.objects.filter(code__in=codes)}
    missing = codes - set(accounts)
    if missing:
        raise LedgerError(f'Unknown ledger account(s): {sorted(missing)}.')

    entry = LedgerEntry.objects.create(
        description=description,
        source_type=source_type,
        source_id=source_id,
        kind=kind,
        event=event,
        created_by=created_by,
        reverses=reverses,
    )
    LedgerLine.objects.bulk_create([
        LedgerLine(entry=entry, account=accounts[code], debit=debit, credit=credit)
        for code, debit, credit in lines
    ])
    return entry


def account_balance(code):
    """Balance of one account in paise, always computed from ledger lines.

    Assets and expenses grow with debits; revenue and liabilities grow with
    credits. Plan: "Never store a running balance as an editable field."
    """
    account = LedgerAccount.objects.get(code=code)
    totals = LedgerLine.objects.filter(account=account).aggregate(
        debit=Sum('debit', default=0), credit=Sum('credit', default=0),
    )
    if account.type in (LedgerAccount.Type.ASSET, LedgerAccount.Type.EXPENSE):
        return totals['debit'] - totals['credit']
    return totals['credit'] - totals['debit']
