from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import has_role

from . import expenses, reports
from .models import ExpenseRequest, LedgerEntry
from .serializers import (
    DecisionSerializer, ExpenseSerializer, ExpenseSubmitSerializer, LedgerEntrySerializer, RejectionSerializer,
)

# Plan permission table: "Approve or reject expense" and "See ledger, trace,
# reconciliation" are president and treasurer.
Finance = has_role('president', 'treasurer')


class SelfApprovalError(PermissionDenied):
    default_detail = 'You cannot decide or pay your own expense request.'
    default_code = 'self_approval'


class InvalidTransitionError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'invalid_status'


EXPENSES = ExpenseRequest.objects.select_related('requester', 'approval__approver')


class ExpenseListCreateView(APIView):
    """POST /expenses (any logged-in user, multipart with the receipt),
    GET /expenses (president and treasurer: the approval queue).
    """

    # multipart for the file upload; JSON is kept so a request without a
    # file gets a field error rather than a 415.
    parser_classes = [MultiPartParser, JSONParser]

    def get_permissions(self):
        return [Finance()] if self.request.method == 'GET' else [IsAuthenticated()]

    def get(self, request):
        queryset = EXPENSES.all()
        wanted = request.query_params.get('status')
        if wanted:
            if wanted not in ExpenseRequest.Status.values:
                raise ValidationError({'status': [ErrorDetail('Unknown status.', code='invalid_choice')]})
            queryset = queryset.filter(status=wanted)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request)
        data = ExpenseSerializer(page, many=True, context={'request': request}).data
        return paginator.get_paginated_response(data)

    def post(self, request):
        serializer = ExpenseSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # The requester is the token's user; the status is always submitted.
        expense = serializer.save(requester=request.user)
        return Response(ExpenseSerializer(expense, context={'request': request}).data, status=status.HTTP_201_CREATED)


class MyExpensesView(ListAPIView):
    """GET /expenses/me. Plan: "Members can read only their own ... expenses"."""

    permission_classes = [IsAuthenticated]
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        return EXPENSES.filter(requester=self.request.user)


class ExpenseDecisionView(APIView):
    """POST /expenses/{id}/approve, /reject, /mark-paid. President or
    treasurer, and never the requester.
    """

    permission_classes = [Finance]
    action = None

    def post(self, request, pk):
        get_object_or_404(ExpenseRequest, pk=pk)
        try:
            if self.action == 'approve':
                data = DecisionSerializer(data=request.data)
                data.is_valid(raise_exception=True)
                expenses.approve(pk, request.user, data.validated_data['reason'])
            elif self.action == 'reject':
                data = RejectionSerializer(data=request.data)
                data.is_valid(raise_exception=True)
                expenses.reject(pk, request.user, data.validated_data['reason'])
            else:
                expenses.mark_paid(pk, request.user)
        except expenses.SelfApproval:
            raise SelfApprovalError()
        except expenses.InvalidTransition as exc:
            raise InvalidTransitionError(str(exc))
        expense = EXPENSES.get(pk=pk)
        return Response(ExpenseSerializer(expense, context={'request': request}).data)


class SummaryView(APIView):
    """GET /finance/summary. The one-page treasurer view (R17)."""

    permission_classes = [Finance]

    def get(self, request):
        return Response(reports.summary())


class LedgerListView(ListAPIView):
    """GET /finance/ledger. Filter with ?account=<code>, ?event=<id>, ?kind=."""

    permission_classes = [Finance]
    serializer_class = LedgerEntrySerializer

    def get_queryset(self):
        entries = LedgerEntry.objects.prefetch_related('lines__account').order_by('-posted_at', '-id')
        params = self.request.query_params
        if params.get('account'):
            entries = entries.filter(lines__account__code=params['account']).distinct()
        if params.get('event'):
            if not params['event'].isdigit():
                raise ValidationError({'event': [ErrorDetail('Must be an event id.', code='invalid')]})
            entries = entries.filter(event_id=int(params['event']))
        if params.get('kind'):
            entries = entries.filter(kind=params['kind'])
        return entries


class ReconcileView(APIView):
    """GET /finance/reconcile."""

    permission_classes = [Finance]

    def get(self, request):
        return Response(reports.reconcile())


class TraceView(APIView):
    """GET /finance/trace?figure=... The Coin Trail."""

    permission_classes = [Finance]

    def get(self, request):
        figure = request.query_params.get('figure', '')
        try:
            return Response(reports.trace(figure))
        except reports.UnknownFigure:
            raise ValidationError({'figure': [ErrorDetail(
                'Use came_in, went_out, cash, payable, account:<code>, or '
                'event:<id>:revenue|expenses|profit.', code='unknown_figure',
            )]})
