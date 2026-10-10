from django.contrib import admin

from .models import MembershipPlan


# Plans are created here until the seed script exists. Memberships, orders,
# payments and ledger rows are deliberately not editable in the admin: they
# must only come from the purchase flow.
@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'duration_months', 'ticket_discount_pct', 'merch_discount_pct', 'active']
    list_filter = ['active']
