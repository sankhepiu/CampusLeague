from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import has_role
from members.services import membership_status
from shop.api import IdempotencyKeyReused, PaymentFailed, idempotency_key
from shop.models import Order
from shop.payments import IdempotencyConflict, SalesClosed, purchase_tickets
from shop.serializers import OrderSerializer, PaymentSerializer

from . import tickets
from .models import Event, Ticket, TicketTier
from .serializers import (
    CheckInRequestSerializer, EventSerializer, EventWriteSerializer, TicketPurchaseSerializer,
    TicketSerializer, TierSerializer, TierWriteSerializer,
)

# Plan permission table: "Create events and tiers" and "Check people in" are
# president and event manager only.
EventStaff = has_role('president', 'event_manager')


class SoldOutError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Sold out: not enough seats are left in this tier.'
    default_code = 'sold_out'


class SalesClosedError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Tickets for this tier are not on sale right now.'
    default_code = 'sales_closed'


def is_event_staff(request):
    return EventStaff().has_permission(request, None)


def visible_events(request):
    """ASSUMPTION (plan is silent): draft events are visible to event staff
    only; everyone else gets a 404 for them.
    """
    events = Event.objects.prefetch_related('tiers')
    return events if is_event_staff(request) else events.exclude(status=Event.Status.DRAFT)


def price_context(request):
    user = request.user
    return {'is_member': user.is_authenticated and membership_status(user) == 'active'}


class StaffWriteMixin:
    """Reads are public; writes need the event-staff role."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [EventStaff()]


class EventListCreateView(StaffWriteMixin, ListCreateAPIView):
    """GET /events (public), POST /events (event staff)."""

    def get_queryset(self):
        return visible_events(self.request)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **price_context(self.request)}

    def get_serializer_class(self):
        return EventSerializer if self.request.method == 'GET' else EventWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = EventWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)


class EventDetailView(StaffWriteMixin, RetrieveUpdateAPIView):
    """GET /events/{id} (public), PATCH /events/{id} (event staff)."""

    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return visible_events(self.request)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **price_context(self.request)}

    def get_serializer_class(self):
        return EventSerializer if self.request.method == 'GET' else EventWriteSerializer

    def partial_update(self, request, *args, **kwargs):
        with transaction.atomic():
            # Locked so capacity_total cannot be lowered while a tier is
            # being added.
            event = get_object_or_404(Event.objects.select_for_update(), pk=kwargs['pk'])
            serializer = EventWriteSerializer(event, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response(EventSerializer(event).data)


class TierCreateView(APIView):
    """POST /events/{id}/tiers. Event staff."""

    permission_classes = [EventStaff]

    def post(self, request, pk):
        with transaction.atomic():
            event = get_object_or_404(Event.objects.select_for_update(), pk=pk)
            serializer = TierWriteSerializer(data=request.data, context={'event': event})
            serializer.is_valid(raise_exception=True)
            tier = serializer.save(event=event)
        return Response(TierSerializer(tier).data, status=status.HTTP_201_CREATED)


class TicketPurchaseView(APIView):
    """POST /events/{id}/tickets. Any logged-in user."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        key = idempotency_key(request)
        event = get_object_or_404(visible_events(request), pk=pk)
        serializer = TicketPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not TicketTier.objects.filter(pk=data['tier'], event=event).exists():
            raise ValidationError(
                {'tier': [ErrorDetail('This event has no such tier.', code='does_not_exist')]}
            )

        try:
            result = purchase_tickets(
                # Buyer from the token; price worked out on the server.
                user=request.user,
                tier_id=data['tier'],
                quantity=data['quantity'],
                outcome=data['test_outcome'],
                idempotency_key=key,
            )
        except tickets.SoldOut:
            raise SoldOutError()
        except SalesClosed:
            raise SalesClosedError()
        except IdempotencyConflict:
            raise IdempotencyKeyReused()

        if result.order.status == Order.Status.CANCELLED:
            raise PaymentFailed()
        body = {
            'order': OrderSerializer(result.order).data,
            'payment': PaymentSerializer(result.payment).data if result.payment else None,
            'tickets': TicketSerializer(result.tickets, many=True).data,
        }
        if result.order.status == Order.Status.PENDING:
            return Response(body, status=status.HTTP_202_ACCEPTED)
        return Response(body, status=status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED)


class MyTicketsView(ListAPIView):
    """GET /tickets/me. Plan: "Members can read only their own tickets"."""

    permission_classes = [IsAuthenticated]
    serializer_class = TicketSerializer

    def get_queryset(self):
        return Ticket.objects.filter(owner=self.request.user).select_related('event', 'tier')


class CheckInView(APIView):
    """POST /checkin. Plan: "limited to event manager and president, since
    it reveals member status."
    """

    permission_classes = [EventStaff]

    def post(self, request):
        serializer = CheckInRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scan = tickets.scan(
            operator=request.user, token=data['token'], code=data['code'], event_id=data['event'],
        )

        ticket, checkin = scan.ticket, scan.checkin
        # Plan: "one result object with: result, ticket summary, holder name,
        # membership status, and original check-in time when duplicate."
        # Always 200: "invalid" is an answer for the door, not a client bug.
        return Response({
            'result': scan.result,
            'ticket': ticket and {
                'id': ticket.id,
                'code': ticket.code,
                'status': ticket.status,
                'event': {'id': ticket.event_id, 'title': ticket.event.title},
                'tier': {'id': ticket.tier_id, 'name': ticket.tier.name},
            },
            'holder_name': ticket and ticket.owner.name,
            'membership_status': scan.membership_status,
            'checked_in_at': checkin and checkin.scanned_at,
            'checked_in_by': checkin and checkin.scanned_by.name,
        })
