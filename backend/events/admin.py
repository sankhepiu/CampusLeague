from django.contrib import admin

from common.admin import ReadOnlyAdmin, rupees

from .models import CheckIn, Event, Ticket, TicketTier


@admin.register(Event)
class EventAdmin(ReadOnlyAdmin):
    list_display = ['title', 'venue', 'starts_at', 'status', 'capacity_total', 'budget']
    list_filter = ['status']

    @admin.display(description='Budget', ordering='budget_amount')
    def budget(self, event):
        return rupees(event.budget_amount)


@admin.register(TicketTier)
class TicketTierAdmin(ReadOnlyAdmin):
    list_display = ['event', 'name', 'public', 'member', 'capacity', 'sold_count', 'seats_left']
    list_select_related = ['event']

    @admin.display(description='Public price', ordering='public_price')
    def public(self, tier):
        return rupees(tier.public_price)

    @admin.display(description='Member price', ordering='member_price')
    def member(self, tier):
        return rupees(tier.member_price)


@admin.register(Ticket)
class TicketAdmin(ReadOnlyAdmin):
    list_display = ['code', 'event', 'tier', 'owner', 'status', 'paid']
    list_filter = ['status', 'event']
    search_fields = ['code', 'owner__email', 'owner__name']
    list_select_related = ['event', 'tier', 'owner']
    # The signed token is a bearer credential for the door; not shown here.
    exclude = ['qr_token']

    @admin.display(description='Price paid', ordering='price_paid')
    def paid(self, ticket):
        return rupees(ticket.price_paid)


@admin.register(CheckIn)
class CheckInAdmin(ReadOnlyAdmin):
    list_display = ['ticket', 'scanned_by', 'scanned_at', 'member_status_at_scan']
    list_select_related = ['ticket', 'scanned_by']
