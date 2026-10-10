from rest_framework import serializers

from . import services
from .models import Announcement, AnnouncementDelivery


class AnnouncementSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    deliveries = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ['id', 'title', 'body', 'audience', 'author', 'published_at', 'deliveries']
        read_only_fields = fields

    def get_author(self, announcement):
        return {'id': announcement.author_id, 'name': announcement.author.name}

    def get_deliveries(self, announcement):
        # Delivery counts are for the people who post announcements; the
        # public archive gets null.
        return services.delivery_summary(announcement) if self.context.get('show_deliveries') else None


class AnnouncementWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        # author and published_at are set by the server.
        fields = ['title', 'body', 'audience']


class DeliverySerializer(serializers.ModelSerializer):
    recipient = serializers.SerializerMethodField()

    class Meta:
        model = AnnouncementDelivery
        fields = ['id', 'recipient', 'status', 'attempts', 'last_error', 'updated_at']
        read_only_fields = fields

    def get_recipient(self, delivery):
        return {'id': delivery.recipient_id, 'name': delivery.recipient.name, 'email': delivery.recipient.email}
