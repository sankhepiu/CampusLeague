from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import has_role
from finance import reports
from members.services import membership_status
from shop.api import PaymentFailed, idempotency_key, purchase_errors, require_mock_gateway
from shop.models import Order
from shop.payments import SalesClosed, purchase_tickets
from shop.serializers import OrderSerializer, PaymentSerializer

from . import tickets
from .models import CheckIn, Event, TicketPass, TicketTier
from .serializers import (
    CheckInRequestSerializer, EventSerializer, EventWriteSerializer, PassSerializer, TicketPurchaseSerializer,
    TicketSerializer, TierSerializer, TierWriteSerializer, passes_for,
)

# Plan permission table: "Create events and tiers" and "Check people in" are
# president and event manager only.
EventStaff = has_role('president', 'event_manager')
# ASSUMPTION (the plan limits check-in to event manager and president): the
# volunteer coordinator staffs the door too, so they may scan as well.
DoorStaff = has_role('president', 'event_manager', 'volunteer_coordinator')
# Plan API table: attendance and P&L are for EM, P and T.
EventReportReaders = has_role('president', 'event_manager', 'treasurer')


class SoldOutError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Sold out: not enough seats are left in this tier.'
    default_code = 'sold_out'


ORGANISER_FALLBACK = 'Skyline Student Association'


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


def event_overview(event, request):
    """The extra fields of GET /events/{id}: totals for everyone, the
    caller's own passes, and money figures for event staff only.
    """
    tiers = list(event.tiers.all())
    sold = sum(tier.sold_count for tier in tiers)
    checked_in = CheckIn.objects.filter(ticket__event=event).count()
    user = request.user
    overview = {
        # ASSUMPTION: the organiser is whoever created the event. Events
        # made before that was recorded show the club's name.
        'organiser': {'name': event.created_by.name if event.created_by else ORGANISER_FALLBACK},
        'capacity': event.capacity_total,
        'sold': sold,
        # Seats still buyable: what is left in the tiers, not capacity
        # that no tier has been given.
        'seats_left': sum(tier.seats_left for tier in tiers),
        'checked_in': checked_in,
        'my_passes': (
            PassSerializer(passes_for(TicketPass.objects.filter(owner=user, event=event)), many=True).data
            if user.is_authenticated else []
        ),
    }
    if is_event_staff(request):
        overview['revenue'] = reports.event_pnl(event)['revenue']['total']
        overview['attendance_pct'] = round(checked_in * 100 / sold, 1) if sold else None
    return overview


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
        event = serializer.save(created_by=request.user)
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

    def retrieve(self, request, *args, **kwargs):
        event = self.get_object()
        return Response({**self.get_serializer(event).data, **event_overview(event, request)})

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
        require_mock_gateway()
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
            with purchase_errors():
                result = purchase_tickets(
                    # Buyer from the token; price worked out on the server.
                    user=request.user,
                    tier_id=data['tier'],
                    quantity=data['quantity'],
                    outcome=data['test_outcome'],
                    idempotency_key=key,
                    coupon=data['coupon'],
                )
        except tickets.SoldOut:
            raise SoldOutError()
        except SalesClosed:
            raise SalesClosedError()

        if result.order.status == Order.Status.CANCELLED:
            raise PaymentFailed()
        body = {
            'order': OrderSerializer(result.order).data,
            'payment': PaymentSerializer(result.payment).data if result.payment else None,
            'tickets': TicketSerializer(result.tickets, many=True).data,
            # The one QR code for all of them; null until the order is paid.
            'pass': pass_for_order(result.order),
        }
        if result.order.status == Order.Status.PENDING:
            return Response(body, status=status.HTTP_202_ACCEPTED)
        return Response(body, status=status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED)


def pass_for_order(order):
    ticket_pass = passes_for(TicketPass.objects.filter(order=order)).first()
    return PassSerializer(ticket_pass).data if ticket_pass else None


class MyTicketsView(ListAPIView):
    """GET /tickets/me. Plan: "Members can read only their own tickets".
    Returned as group passes, one per purchase, each listing its tickets.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PassSerializer

    def get_queryset(self):
        return passes_for(TicketPass.objects.filter(owner=self.request.user))


class PassDetailView(APIView):
    """GET /tickets/passes/{id}. The owner, or anyone who may work the
    door. Everyone else gets a 404, as for a pass that does not exist.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        passes = passes_for(TicketPass.objects.select_related('owner'))
        if not DoorStaff().has_permission(request, self):
            passes = passes.filter(owner=request.user)
        ticket_pass = get_object_or_404(passes, pk=pk)
        return Response({
            **PassSerializer(ticket_pass).data,
            'order': ticket_pass.order_id,
            'holder': {'name': ticket_pass.owner.name},
            'history': [
                {**item, 'at': timezone.localtime(item['at'])} for item in tickets.pass_history(ticket_pass)
            ],
        })


class CheckInView(APIView):
    """POST /checkin. Restricted to door staff because it reveals member
    status. Takes a ticket (token or code) or a member card (member_token).
    """

    permission_classes = [DoorStaff]

    def post(self, request):
        serializer = CheckInRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['member_token']:
            result, holder, status = tickets.scan_member(data['member_token'])
            return Response({
                'result': result,
                'holder': holder and {'name': holder.name, 'email': holder.email},
                'membership_status': status,
            })
        # A pass token may arrive as `token`: the scanner need not know
        # which kind of QR code it read.
        pass_token = data['pass_token'] or (data['token'] if tickets.read_pass_token(data['token']) else '')
        if pass_token:
            return self.scan_pass(request, pass_token, data)
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
            # In the site's time zone (+05:30), like every other timestamp.
            'checked_in_at': checkin and timezone.localtime(checkin.scanned_at),
            'checked_in_by': checkin and checkin.scanned_by.name,
        })


    def scan_pass(self, request, token, data):
        try:
            scan = tickets.scan_pass(
                operator=request.user, token=token, count=data['count'], event_id=data['event'],
            )
        except tickets.TooManyForPass as exc:
            raise ValidationError({'count': [ErrorDetail(
                f'Only {exc.remaining} left on this pass.', code='exceeds_remaining',
            )]})
        ticket_pass = scan.ticket_pass
        # Always 200, like a ticket scan. The keys are always the same;
        # those that do not apply to the result are null.
        return Response({
            'result': scan.result,
            'pass_id': ticket_pass and ticket_pass.id,
            'admitted': scan.admitted if ticket_pass else None,
            'admitted_now': scan.admitted_now if ticket_pass else None,
            'total': scan.total if ticket_pass else None,
            'remaining': scan.remaining if ticket_pass else None,
            'holder': ticket_pass and {'name': ticket_pass.owner.name},
            'membership_status': scan.membership_status,
            'event': ticket_pass and {
                'id': ticket_pass.event_id, 'name': ticket_pass.event.title, 'title': ticket_pass.event.title,
            },
            'tier': ticket_pass and {'id': ticket_pass.tier_id, 'name': ticket_pass.tier.name},
        })


class EventAttendanceView(APIView):
    """GET /events/{id}/attendance. Plan: "Sold, checked in, no-shows"."""

    permission_classes = [EventReportReaders]

    def get(self, request, pk):
        event = get_object_or_404(Event.objects.prefetch_related('tiers'), pk=pk)
        return Response({'event': {'id': event.id, 'title': event.title, 'status': event.status},
                         **reports.event_attendance(event)})


class EventPnlView(APIView):
    """GET /events/{id}/pnl. Plan: "Revenue, expenses, profit, budget vs
    actual", plus the attendance rate.
    """

    permission_classes = [EventReportReaders]

    def get(self, request, pk):
        event = get_object_or_404(Event.objects.prefetch_related('tiers'), pk=pk)
        attendance = reports.event_attendance(event)
        return Response({
            'event': {'id': event.id, 'title': event.title, 'status': event.status},
            **reports.event_pnl(event),
            'attendance': {key: attendance[key] for key in ('sold', 'checked_in', 'attendance_rate_pct')},
        })
