from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import RoleAssignment, User


# Until the president-only /roles endpoint exists, roles are assigned here.
@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'term_start', 'term_end']
    list_filter = ['role']
    search_fields = ['user__email', 'user__name']


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Django's UserAdmin assumes username/first_name/last_name, so every
    # option that names those fields is redefined for our email-based model.
    ordering = ['email']
    list_display = ['email', 'name', 'college_id', 'is_active', 'is_staff']
    search_fields = ['email', 'name', 'college_id']
    fieldsets = [
        (None, {'fields': ['email', 'password']}),
        ('Profile', {'fields': ['name', 'college_id', 'phone']}),
        ('Admin access', {'fields': ['is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions']}),
    ]
    add_fieldsets = [
        (None, {'fields': ['email', 'name', 'college_id', 'password1', 'password2']}),
    ]
