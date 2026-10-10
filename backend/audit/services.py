from .models import AuditLog


def record(*, actor, action, obj, before=None, after=None):
    """Write one audit row. Call it inside the same transaction as the
    change it describes, so a change can never exist without its log row.
    """
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=obj._meta.label_lower,
        object_id=obj.pk,
        before=before,
        after=after,
    )
