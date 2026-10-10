"""Shared pieces for the Django admin's read-only views.

The admin is a window onto the data for the demo, not a way to change it:
money, tickets, stock and the audit trail may only change through the
application's own flows.
"""
from django.contrib import admin


def rupees(paise):
    """Paise as a rupee string, for display only."""
    return '' if paise is None else f'Rs {paise / 100:,.2f}'


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """List and view pages only: no add, edit or delete."""

    actions = None       # removes the "delete selected" action as well


class ReadOnlyInline(ReadOnlyMixin, admin.TabularInline):
    extra = 0
    can_delete = False
