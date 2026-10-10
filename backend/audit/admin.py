from django.contrib import admin

from common.admin import ReadOnlyAdmin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdmin):
    list_display = ['at', 'actor', 'action', 'object_type', 'object_id']
    list_filter = ['action']
    search_fields = ['action', 'actor__email']
    list_select_related = ['actor']
