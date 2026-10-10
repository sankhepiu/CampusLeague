from rest_framework.generics import ListAPIView

from accounts.permissions import has_role

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogListView(ListAPIView):
    """GET /audit. Plan API table: "Audit: GET /audit, P, Audit log".
    Newest first. ?action=<name> keeps only rows with exactly that action.
    """

    permission_classes = [has_role('president')]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        # Model ordering is newest first (-at, -id).
        logs = AuditLog.objects.select_related('actor')
        action = self.request.query_params.get('action')
        return logs.filter(action=action) if action else logs
