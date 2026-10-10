from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.permissions import has_role

from . import services
from .models import Announcement, AnnouncementDelivery
from .serializers import AnnouncementSerializer, AnnouncementWriteSerializer, DeliverySerializer

# Plan permission table: "Post announcements" is P, EM and VC.
CommsStaff = has_role('president', 'event_manager', 'volunteer_coordinator')


class ArchiveMixin:
    queryset = Announcement.objects.select_related('author')
    serializer_class = AnnouncementSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [CommsStaff()]

    def get_serializer_context(self):
        staff = CommsStaff().has_permission(self.request, self)
        return {**super().get_serializer_context(), 'show_deliveries': staff}


class AnnouncementListCreateView(ArchiveMixin, ListCreateAPIView):
    """GET /announcements (public archive), POST /announcements (comms staff)."""

    def create(self, request, *args, **kwargs):
        serializer = AnnouncementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Step 1: save and queue (its own committed transaction).
        announcement = services.publish(author=request.user, **serializer.validated_data)
        # Step 2: email. A failure here changes delivery rows only; the
        # announcement above is already saved. Sent in the request for now,
        # which is fine for the console backend but would be slow with real
        # SMTP and many recipients.
        services.send_pending(announcement)
        body = AnnouncementSerializer(announcement, context={'show_deliveries': True}).data
        return Response(body, status=status.HTTP_201_CREATED)


class AnnouncementDetailView(ArchiveMixin, RetrieveAPIView):
    """GET /announcements/{id}. Public."""


class DeliveryListView(ListAPIView):
    """GET /announcements/{id}/deliveries. The delivery log, comms staff only
    (it lists recipients' email addresses).
    """

    permission_classes = [CommsStaff]
    serializer_class = DeliverySerializer

    def get_queryset(self):
        announcement = get_object_or_404(Announcement, pk=self.kwargs['pk'])
        return AnnouncementDelivery.objects.filter(announcement=announcement).select_related('recipient')
