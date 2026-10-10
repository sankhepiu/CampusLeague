from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'action', 'object_type', 'object_id', 'before', 'after', 'at']
        read_only_fields = fields

    def get_actor(self, log):
        return log.actor and {'id': log.actor_id, 'name': log.actor.name}
