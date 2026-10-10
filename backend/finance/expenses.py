"""The reimbursement state machine.

    submitted --approve--> approved --mark_paid--> paid
        \\------reject---> rejected

Plan: "Expense status changes only through the approval endpoint, which also
posts the ledger entry in the same transaction."
"""
from django.db import transaction

from audit import services as audit

from .models import Approval, ExpenseRequest, LedgerEntry
from .services import post_entry

CASH = '1000'
REIMBURSEMENTS_PAYABLE = '2000'
EXPENSE_ACCOUNT = {
    ExpenseRequest.Category.EVENT: '5000',
    ExpenseRequest.Category.FUNDRAISER: '5100',
    ExpenseRequest.Category.GENERAL: '5200',
}

Status = ExpenseRequest.Status


class SelfApproval(Exception):
    """The actor is the person who submitted the request."""


class InvalidTransition(Exception):
    def __init__(self, expense, action):
        self.status = expense.status
        super().__init__(f'Cannot {action} a request that is {expense.status}.')


def _locked(expense_id, actor, action, required_status):
    """Fetch the request under a row lock and check the two rules every
    decision shares. The lock makes two simultaneous decisions take turns,
    so the second sees the first one's status change and is refused.
    """
    expense = ExpenseRequest.objects.select_for_update().get(pk=expense_id)
    # Plan: "Approval is refused if approver equals requester." Checked here
    # as well as in the view, so no caller can skip it.
    if expense.requester_id == actor.pk:
        raise SelfApproval()
    if expense.status != required_status:
        raise InvalidTransition(expense, action)
    return expense


def _set_status(expense, status, actor, action):
    before = expense.status
    expense.status = status
    expense.save(update_fields=['status', 'updated_at'])
    audit.record(actor=actor, action=action, obj=expense, before={'status': before}, after={'status': status})


@transaction.atomic
def approve(expense_id, approver, reason=''):
    """Approve: Approval row, status, audit row and ledger entry together.
    Plan posting rule: debit the expense account (by category, tagged with
    the event), credit Reimbursements payable.
    """
    expense = _locked(expense_id, approver, 'approve', Status.SUBMITTED)
    Approval.objects.create(
        expense=expense, approver=approver, decision=Approval.Decision.APPROVED, reason=reason,
    )
    _set_status(expense, Status.APPROVED, approver, 'expense.approved')
    post_entry(
        description=f'Expense approved: {expense.description}'[:255],
        source_type=LedgerEntry.SourceType.EXPENSE_REQUEST,
        source_id=expense.pk,
        kind=LedgerEntry.Kind.EXPENSE_APPROVED,
        event=expense.event,
        created_by=approver,
        lines=[(EXPENSE_ACCOUNT[expense.category], expense.amount, 0), (REIMBURSEMENTS_PAYABLE, 0, expense.amount)],
    )
    return expense


@transaction.atomic
def reject(expense_id, approver, reason):
    """Reject: nothing is owed, so nothing is posted to the ledger."""
    expense = _locked(expense_id, approver, 'reject', Status.SUBMITTED)
    Approval.objects.create(
        expense=expense, approver=approver, decision=Approval.Decision.REJECTED, reason=reason,
    )
    _set_status(expense, Status.REJECTED, approver, 'expense.rejected')
    return expense


@transaction.atomic
def mark_paid(expense_id, payer):
    """Pay out an approved request. Plan posting rule: debit Reimbursements
    payable, credit Cash. A second entry for the same source, told apart by
    kind, so "approved" and "paid" stay separate in the ledger.
    """
    expense = _locked(expense_id, payer, 'pay', Status.APPROVED)
    _set_status(expense, Status.PAID, payer, 'expense.paid')
    post_entry(
        description=f'Reimbursement paid: {expense.description}'[:255],
        source_type=LedgerEntry.SourceType.EXPENSE_REQUEST,
        source_id=expense.pk,
        kind=LedgerEntry.Kind.EXPENSE_PAID,
        event=expense.event,
        created_by=payer,
        lines=[(REIMBURSEMENTS_PAYABLE, expense.amount, 0), (CASH, 0, expense.amount)],
    )
    return expense
