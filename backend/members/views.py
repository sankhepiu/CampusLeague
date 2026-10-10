from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import RoleAssignment
from accounts.permissions import has_role
from shop.api import IdempotencyKeyReused, PaymentFailed, idempotency_key
from shop.models import Order
from shop.payments import IdempotencyConflict, purchase_membership
from shop.serializers import OrderSerializer, PaymentSerializer

from . import services
from .models import MembershipPlan
from .serializers import (
    MemberSerializer, MembershipPurchaseSerializer, MembershipSerializer, PlanSerializer,
)


class PlanListView(ListAPIView):
    """GET /plans. Public."""

    permission_classes = [AllowAny]
    serializer_class = PlanSerializer
    queryset = MembershipPlan.objects.filter(active=True)


class MembershipPurchaseView(APIView):
    """POST /memberships. Any logged-in user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        key = idempotency_key(request)
        serializer = MembershipPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = purchase_membership(
                # The buyer is the token's user, never a value from the body.
                user=request.user,
                plan=serializer.validated_data['plan'],
                outcome=serializer.validated_data['test_outcome'],
                idempotency_key=key,
            )
        except IdempotencyConflict:
            raise IdempotencyKeyReused()

        if result.order.status == Order.Status.CANCELLED:
            raise PaymentFailed()

        body = {
            'order': OrderSerializer(result.order).data,
            'payment': PaymentSerializer(result.payment).data if result.payment else None,
            'membership': MembershipSerializer(result.membership).data if result.membership else None,
        }
        if result.order.status == Order.Status.PENDING:
            return Response(body, status=status.HTTP_202_ACCEPTED)
        # ASSUMPTION: a replay returns the first result with 200, not 201,
        # because nothing new was created.
        return Response(body, status=status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED)


class MyMembershipView(APIView):
    """GET /memberships/me. Plan: "My status, expiry, benefits"."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        current = services.current_membership(user)
        return Response({
            'status': services.membership_status(user),
            # Benefits are on membership.plan.
            'membership': MembershipSerializer(current).data if current else None,
            'paid_until': services.paid_until(user),
        })


class MemberListView(ListAPIView):
    """GET /members. Plan API table: "P, T, EM. Member list and detail with
    status."

    ?status=active|lapsed|none filters by membership status.
    ?search=text matches name or email, ignoring case.
    """

    permission_classes = [has_role('president', 'treasurer', 'event_manager')]
    serializer_class = MemberSerializer

    def get_queryset(self):
        today = timezone.localdate()
        users = services.with_membership_status(get_user_model().objects.all(), today).prefetch_related(
            Prefetch(
                'role_assignments',
                queryset=RoleAssignment.objects.filter(term_start__lte=today, term_end__gte=today),
                to_attr='current_assignments',
            )
        ).order_by('name', 'id')

        params = self.request.query_params
        wanted = params.get('status')
        if wanted:
            if wanted not in ('active', 'lapsed', 'none'):
                raise ValidationError(
                    {'status': [ErrorDetail('Use active, lapsed or none.', code='invalid_choice')]}
                )
            users = users.filter(membership_status=wanted)
        search = params.get('search', '').strip()
        if search:
            users = users.filter(Q(name__icontains=search) | Q(email__icontains=search))
        return users
