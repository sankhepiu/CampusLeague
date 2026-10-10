from django.db.models import Sum
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from shop.payments import OUTCOMES, SUCCESS

from .models import Event, Ticket, TicketTier

# ASSUMPTION (plan is silent): at most this many tickets in one purchase.
MAX_TICKETS_PER_ORDER = 10


def error(message, code):
    return [ErrorDetail(message, code=code)]


class TierSerializer(serializers.ModelSerializer):
    """A tier as buyers see it. `price` is what the caller would pay now."""

    price = serializers.SerializerMethodField()
    seats_left = serializers.IntegerField(read_only=True)

    class Meta:
        model = TicketTier
        fields = [
            'id', 'name', 'public_price', 'member_price', 'price',
            'capacity', 'seats_left', 'sale_opens', 'sale_closes',
        ]
        read_only_fields = fields

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
    capacity_total = serializers.IntegerField(min_value=1)
    budget_amount = serializers.IntegerField(min_value=0, required=False)

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
        if event and 'capacity_total' in attrs:
            allocated = event.tiers.aggregate(total=Sum('capacity', default=0))['total']
            if attrs['capacity_total'] < allocated:
                raise serializers.ValidationError({'capacity_total': error(
                    f'The tiers already allocate {allocated} seats.', 'below_tier_capacity',
                )})
        return attrs


class TierWriteSerializer(serializers.ModelSerializer):
    public_price = serializers.IntegerField(min_value=1)
    member_price = serializers.IntegerField(min_value=1)
    capacity = serializers.IntegerField(min_value=1)

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
    # ASSUMPTION (not in the plan): the scanner may say which event it is
    # working; a ticket for any other event is then reported as invalid.
    event = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)

    def validate(self, attrs):
        given = [name for name in ('token', 'code', 'member_token') if attrs[name]]
        if len(given) != 1:
            raise serializers.ValidationError(
                error('Send exactly one of token, code or member_token.', 'token_or_code_required')
            )
        return attrs
