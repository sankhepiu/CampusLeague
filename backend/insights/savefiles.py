from django.db import transaction

from audit import services as audit
from events.models import Event

from .models import SaveFile

FIELDS = ['vendors', 'budget_notes', 'what_worked', 'what_didnt', 'checklist']


@transaction.atomic
def save(*, event, actor, **changes):
    """Create the event's save file, or update the one it has. Returns
    (save_file, created). Only the fields given are changed, and every
    change is written to the audit log in the same transaction.
    """
    # Row lock on the event: two people saving at once take turns, so the
    # second updates the first one's file instead of colliding with it.
    Event.objects.select_for_update().get(pk=event.pk)
    existing = SaveFile.objects.filter(event=event).first()
    if existing is None:
        save_file = SaveFile.objects.create(event=event, **changes)
        audit.record(
            actor=actor, action='savefile.created', obj=save_file,
            after={name: getattr(save_file, name) for name in FIELDS},
        )
        return save_file, True

    before = {name: getattr(existing, name) for name in changes}
    changed = {name: value for name, value in changes.items() if before[name] != value}
    if changed:
        for name, value in changed.items():
            setattr(existing, name, value)
        existing.save(update_fields=[*changed, 'updated_at'])
        audit.record(
            actor=actor, action='savefile.updated', obj=existing,
            before={name: before[name] for name in changed}, after=changed,
        )
    return existing, False
