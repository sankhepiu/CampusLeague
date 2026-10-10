from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import has_role

from . import services
from .models import Fundraiser, Task, TaskAssignment
from .serializers import (
    AssignSerializer, FundraiserSerializer, FundraiserWriteSerializer, SaleSerializer,
    TaskSerializer, TaskStatusSerializer, TaskWriteSerializer,
)

# Plan permission table: "Create fundraisers and tasks" is P and VC.
Coordinators = has_role('president', 'volunteer_coordinator')


def is_coordinator(request):
    return Coordinators().has_permission(request, None)


class MemberReadMixin:
    """Reads need a login (plan: "M"); writes need a coordinator."""

    def get_permissions(self):
        return [IsAuthenticated()] if self.request.method == 'GET' else [Coordinators()]

    def get_serializer_class(self):
        return FundraiserSerializer if self.request.method == 'GET' else FundraiserWriteSerializer


class FundraiserListCreateView(MemberReadMixin, ListCreateAPIView):
    """GET /fundraisers (logged in), POST /fundraisers (coordinators)."""

    queryset = Fundraiser.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = FundraiserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(FundraiserSerializer(serializer.save()).data, status=status.HTTP_201_CREATED)


class FundraiserDetailView(MemberReadMixin, RetrieveUpdateAPIView):
    """GET /fundraisers/{id} (logged in), PATCH (coordinators)."""

    queryset = Fundraiser.objects.all()
    http_method_names = ['get', 'patch', 'head', 'options']

    def partial_update(self, request, *args, **kwargs):
        fundraiser = self.get_object()
        serializer = FundraiserWriteSerializer(fundraiser, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(FundraiserSerializer(fundraiser).data)


class FundraiserSaleView(APIView):
    """POST /fundraisers/{id}/sales. Coordinators.

    Not in the plan's endpoint table: added with the FundraiserSale table
    (team decision) so fundraiser revenue has a way into the ledger.
    """

    permission_classes = [Coordinators]

    def post(self, request, pk):
        fundraiser = get_object_or_404(Fundraiser, pk=pk)
        serializer = SaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.record_sale(fundraiser=fundraiser, recorded_by=request.user, **serializer.validated_data)
        return Response(FundraiserSerializer(fundraiser).data, status=status.HTTP_201_CREATED)


class TaskCreateView(APIView):
    """POST /tasks. Coordinators."""

    permission_classes = [Coordinators]

    def post(self, request):
        serializer = TaskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(TaskSerializer(serializer.save()).data, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
    """PATCH /tasks/{id}. Coordinators."""

    permission_classes = [Coordinators]

    def patch(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        serializer = TaskWriteSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(TaskSerializer(serializer.save()).data)


class TaskAssignView(APIView):
    """POST /tasks/{id}/assign. Coordinators. Assigning the same person
    again updates their role note instead of duplicating them.
    """

    permission_classes = [Coordinators]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        serializer = AssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            TaskAssignment.objects.update_or_create(
                task=task, user=serializer.validated_data['user'],
                defaults={'role_note': serializer.validated_data['role_note']},
            )
        return Response(TaskSerializer(task).data)


class TaskStatusView(APIView):
    """PATCH /tasks/{id}/status. Plan: "Assignee, VC". The president is
    allowed too, as the plan lets them manage tasks.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        task = get_object_or_404(Task, pk=pk)
        # Object-level check: this particular task must be assigned to the
        # caller, unless they are a coordinator.
        is_assignee = task.assignments.filter(user=request.user).exists()
        if not (is_assignee or is_coordinator(request)):
            raise PermissionDenied()
        serializer = TaskStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task.status = serializer.validated_data['status']
        task.save(update_fields=['status', 'updated_at'])
        return Response(TaskSerializer(task).data)
