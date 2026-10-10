import re

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shop.models import Order
from shop.payments import IdempotencyConflict, purchase_membership
from shop.serializers import OrderSerializer, PaymentSerializer

from . import services
from .models import MembershipPlan
from .serializers import MembershipPurchaseSerializer, MembershipSerializer, PlanSerializer

# ASSUMPTION (plan names the key but not how it travels): sent in the
# Idempotency-Key header; 8 to 64 letters, digits, "-" or "_". A UUID fits.
IDEMPOTENCY_KEY_PATTERN = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


class IdempotencyKeyRequired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Send an Idempotency-Key header: 8 to 64 letters, digits, "-" or "_".'
    default_code = 'idempotency_key_required'


class IdempotencyKeyReused(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This Idempotency-Key was already used for a different purchase.'
    default_code = 'idempotency_key_reused'


class PaymentFailed(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = 'The payment was declined. You have not been charged.'
    default_code = 'payment_failed'


class PlanListView(ListAPIView):
    """GET /plans. Public."""

    permission_classes = [AllowAny]
    serializer_class = PlanSerializer
    queryset = MembershipPlan.objects.filter(active=True)


class MembershipPurchaseView(APIView):
    """POST /memberships. Any logged-in user."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        key = request.headers.get('Idempotency-Key', '')
        if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
            raise IdempotencyKeyRequired()
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
