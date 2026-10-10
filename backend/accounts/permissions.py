from rest_framework.permissions import BasePermission


def has_role(*roles):
    """Permission class: logged in AND currently holds one of these roles.

    Plan: "One permission check per endpoint, in one place (a permission
    class or decorator), so it is easy to review." Roles are read from
    RoleAssignment rows whose term includes today, on every request; nothing
    the client sends is consulted.

    Usage: permission_classes = [has_role('president', 'event_manager')]
    """
    allowed = frozenset(roles)

    class HasRole(BasePermission):
        def has_permission(self, request, view):
            user = request.user
            return bool(
                user and user.is_authenticated and allowed.intersection(user.current_roles())
            )

    return HasRole
