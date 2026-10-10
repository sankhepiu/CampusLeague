from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from common.validation import MAX_AMOUNT, MAX_CAPACITY, MAX_DESCRIPTION, MAX_TITLE
from shop.payments import OUTCOMES, SUCCESS

from . import tickets as ticket_services
from .models import Event, Ticket, TicketPass, TicketTier

# ASSUMPTION (plan is silent): at most this many tickets in one purchase.
MAX_TICKETS_PER_ORDER = 10


def error(message, code):
    return [ErrorDetail(message, code=code)]


class TierSerializer(serializers.ModelSerializer):
    """A tier as buyers see it. `price` is what the caller would pay now."""

    price = serializers.SerializerMethodField()
    seats_left = serializers.IntegerField(read_only=True)
    sold = serializers.IntegerField(source='sold_count', read_only=True)
    # Buyable right now as far as dates and event status go. A sold-out
    # tier is still "open": check seats_left as well.
    sale_open = serializers.SerializerMethodField()

    class Meta:
        model = TicketTier
        fields = [
            'id', 'name', 'public_price', 'member_price', 'price',
            'capacity', 'sold', 'seats_left', 'sale_opens', 'sale_closes', 'sale_open',
        ]
        read_only_fields = fields

    def get_sale_open(self, tier):
        return tier.sale_is_open(timezone.now())

    def get_price(self, tier):
        # is_member is worked out once per request by the view, from the
        # token's user. Plan: "member price shown when logged in".
        return tier.member_price if self.context.get('is_member') else tier.public_price


class EventSerializer(serializers.ModelSerializer):
    tiers = TierSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'venue', 'starts_at', 'ends_at',
            'capacity_total', 'status', 'tiers',
        ]
        read_only_fields = fields


class EventWriteSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=MAX_TITLE)
    description = serializers.CharField(max_length=MAX_DESCRIPTION, allow_blank=True, required=False)
    venue = serializers.CharField(max_length=MAX_TITLE)
    capacity_total = serializers.IntegerField(min_value=1, max_value=MAX_CAPACITY)
    budget_amount = serializers.IntegerField(min_value=0, max_value=MAX_AMOUNT, required=False)

    class Meta:
        model = Event
        fields = [
            'title', 'description', 'venue', 'starts_at', 'ends_at',
            'capacity_total', 'status', 'budget_amount',
        ]

    def validate(self, attrs):
        event = self.instance
        starts = attrs.get('starts_at', getattr(event, 'starts_at', None))
        ends = attrs.get('ends_at', getattr(event, 'ends_at', None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError(
                {'ends_at': error('The event must end after it starts.', 'ends_before_start')}
            )
        # ASSUMPTION: an event cannot be created in the past, or moved into
        # it. An existing event whose start is not being changed is left
        # alone, so a past event can still be closed or have a typo fixed.
        moved = 'starts_at' in attrs and (event is None or attrs['starts_at'] != event.starts_at)
        if moved and attrs['starts_at'] <= timezone.now():
            raise serializers.ValidationError(
                {'starts_at': error('The event must start in the future.', 'starts_in_past')}
            )
        if event and ends:
            # Sales cannot run past the end of the event (see the tier rule).
            late = event.tiers.filter(sale_closes__gt=ends).first() or event.tiers.filter(sale_opens__gte=ends).first()
            if late:
                raise serializers.ValidationError({'ends_at': error(
                    f'The sale window of tier "{late.name}" would run past the end of the event.',
                    'before_sale_window',
                )})
        if event and 'capacity_total' in attrs:
            allocated = event.tiers.aggregate(total=Sum('capacity', default=0))['total']
            if attrs['capacity_total'] < allocated:
                raise serializers.ValidationError({'capacity_total': error(
                    f'The tiers already allocate {allocated} seats.', 'below_tier_capacity',
                )})
        return attrs


class TierWriteSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=100)
    public_price = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    member_price = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    capacity = serializers.IntegerField(min_value=1, max_value=MAX_CAPACITY)

    class Meta:
        model = TicketTier
        fields = ['name', 'public_price', 'member_price', 'capacity', 'sale_opens', 'sale_closes']

    def validate(self, attrs):
        # context['event'] is the event row, locked by the view, so two
        # tiers created at once cannot both squeeze under capacity_total.
        event = self.context['event']
        opens, closes = attrs.get('sale_opens'), attrs.get('sale_closes')
        if opens and closes and closes <= opens:
            raise serializers.ValidationError(
                {'sale_closes': error('Sales must close after they open.', 'closes_before_opens')}
            )
        # ASSUMPTION: the sale window lies inside the event: tickets cannot
        # go on sale, or stay on sale, once the event is over.
        if closes and closes > event.ends_at:
            raise serializers.ValidationError(
                {'sale_closes': error('Sales cannot close after the event has ended.', 'outside_event')}
            )
        if opens and opens >= event.ends_at:
            raise serializers.ValidationError(
                {'sale_opens': error('Sales cannot open after the event has ended.', 'outside_event')}
            )
        if event.tiers.filter(name=attrs['name']).exists():
            raise serializers.ValidationError(
                {'name': error('This event already has a tier with this name.', 'tier_name_taken')}
            )
        allocated = event.tiers.aggregate(total=Sum('capacity', default=0))['total']
        if allocated + attrs['capacity'] > event.capacity_total:
            raise serializers.ValidationError({'capacity': error(
                f'Only {event.capacity_total - allocated} of the event\'s '
                f'{event.capacity_total} seats are not yet allocated to a tier.',
                'exceeds_event_capacity',
            )})
        return attrs


class TicketPurchaseSerializer(serializers.Serializer):
    # No price, total or user field: all three come from the server.
    tier = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_TICKETS_PER_ORDER, default=1)
    test_outcome = serializers.ChoiceField(choices=OUTCOMES, default=SUCCESS)
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')


class PassSerializer(serializers.ModelSerializer):
    """A group pass: one QR code for the tickets bought together.

    Reads pass.tickets.all(), so views that list passes prefetch it.
    """

    pass_id = serializers.IntegerField(source='id', read_only=True)
    event = serializers.SerializerMethodField()
    tier = serializers.SerializerMethodField()
    quantity = serializers.SerializerMethodField()
    admitted = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    tickets = serializers.SerializerMethodField()

    class Meta:
        model = TicketPass
        fields = [
            'pass_id', 'event', 'tier', 'quantity', 'admitted', 'remaining', 'qr_token', 'tickets', 'created_at',
        ]
        read_only_fields = fields

    def _counts(self, ticket_pass):
        return ticket_services.pass_counts(ticket_pass.tickets.all())

    def get_event(self, ticket_pass):
        event = ticket_pass.event
        # "name" and "title" are the same value: the event object elsewhere
        # in this API calls it title.
        return {
            'id': event.id, 'name': event.title, 'title': event.title,
            'starts_at': event.starts_at, 'venue': event.venue,
        }

    def get_tier(self, ticket_pass):
        return {'id': ticket_pass.tier_id, 'name': ticket_pass.tier.name}

    def get_quantity(self, ticket_pass):
        return self._counts(ticket_pass)[0]

    def get_admitted(self, ticket_pass):
        return self._counts(ticket_pass)[1]

    def get_remaining(self, ticket_pass):
        total, admitted = self._counts(ticket_pass)
        return total - admitted

    def get_tickets(self, ticket_pass):
        tickets = sorted(ticket_pass.tickets.all(), key=lambda ticket: ticket.id)
        return [{'id': ticket.id, 'code': ticket.code, 'status': ticket.status} for ticket in tickets]


def passes_for(queryset):
    """A TicketPass queryset with everything PassSerializer reads."""
    return queryset.select_related('event', 'tier').prefetch_related('tickets')


class TicketSerializer(serializers.ModelSerializer):
    event = serializers.SerializerMethodField()
    tier = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = ['id', 'code', 'qr_token', 'status', 'price_paid', 'event', 'tier', 'created_at']
        read_only_fields = fields

    def get_event(self, ticket):
        event = ticket.event
        return {'id': event.id, 'title': event.title, 'venue': event.venue, 'starts_at': event.starts_at}

    def get_tier(self, ticket):
        return {'id': ticket.tier_id, 'name': ticket.tier.name}


class CheckInRequestSerializer(serializers.Serializer):
    # Plan: "Body: scanned token or manual code."
    token = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
    # A member card instead of a ticket: reports membership only.
    member_token = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    # A group pass. (A pass token sent as `token` is recognised as well, so
    # a scanner need not know which kind of QR code it has read.)
    pass_token = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    # Group passes only: how many people to admit with this scan.
    count = serializers.IntegerField(min_value=1, max_value=MAX_TICKETS_PER_ORDER, required=False, default=1)
    # ASSUMPTION (not in the plan): the scanner may say which event it is
    # working; a ticket for any other event is then reported as invalid.
    event = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)

    def validate(self, attrs):
        given = [name for name in ('token', 'code', 'member_token', 'pass_token') if attrs[name]]
        if len(given) != 1:
            raise serializers.ValidationError(
                error('Send exactly one of token, code, member_token or pass_token.', 'token_or_code_required')
            )
        return attrs
