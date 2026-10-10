from django.contrib import admin

from common.admin import ReadOnlyAdmin

from .models import SaveFile


@admin.register(SaveFile)
class SaveFileAdmin(ReadOnlyAdmin):
    list_display = ['event', 'updated_at']
    list_select_related = ['event']
