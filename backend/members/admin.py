from django.contrib import admin

from .models import MembershipPlan


# Plans are the one thing still editable in the admin. Orders, tickets, the
# ledger and the rest are registered read-only (see common/admin.py): they
# must only change through the application's own flows.
@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'duration_months', 'ticket_discount_pct', 'merch_discount_pct', 'active']
    list_filter = ['active']
