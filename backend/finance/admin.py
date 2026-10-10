from django.contrib import admin

from common.admin import ReadOnlyAdmin, ReadOnlyInline, rupees

from .models import ExpenseRequest, LedgerAccount, LedgerEntry, LedgerLine


@admin.register(LedgerAccount)
class LedgerAccountAdmin(ReadOnlyAdmin):
    list_display = ['code', 'name', 'type']
    ordering = ['code']


class LedgerLineInline(ReadOnlyInline):
    model = LedgerLine
    fields = ['account', 'debit_rupees', 'credit_rupees']
    readonly_fields = fields

    @admin.display(description='Debit')
    def debit_rupees(self, line):
        return rupees(line.debit) if line.debit else ''

    @admin.display(description='Credit')
    def credit_rupees(self, line):
        return rupees(line.credit) if line.credit else ''


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ['id', 'posted_at', 'kind', 'description', 'amount', 'source_type', 'source_id', 'event']
    list_filter = ['kind', 'source_type']
    search_fields = ['description']
    ordering = ['-posted_at', '-id']
    inlines = [LedgerLineInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('event').prefetch_related('lines')

    @admin.display(description='Amount')
    def amount(self, entry):
        # A balanced entry's size is the total of its debits.
        return rupees(sum(line.debit for line in entry.lines.all()))


@admin.register(ExpenseRequest)
class ExpenseRequestAdmin(ReadOnlyAdmin):
    list_display = ['id', 'requester', 'amount_rupees', 'category', 'description', 'status', 'created_at']
    list_filter = ['status', 'category']
    search_fields = ['description', 'requester__email']
    list_select_related = ['requester']

    @admin.display(description='Amount', ordering='amount')
    def amount_rupees(self, expense):
        return rupees(expense.amount)
