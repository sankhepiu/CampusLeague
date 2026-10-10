from django.core import signing
from django.db import migrations

# Copied from events.tickets on purpose: a migration must keep working even
# if that module changes later.
PASS_QR_SALT = 'campusleague.pass-qr'


def create_passes(apps, schema_editor):
    """Give every ticket sold before group passes existed a pass: one per
    order and tier, exactly as a purchase made today would get.
    """
    Ticket = apps.get_model('events', 'Ticket')
    TicketPass = apps.get_model('events', 'TicketPass')
    groups = (
        Ticket.objects.filter(ticket_pass__isnull=True)
        .values_list('order_id', 'tier_id', 'event_id', 'owner_id').distinct().order_by('order_id', 'tier_id')
    )
    for order_id, tier_id, event_id, owner_id in groups:
        ticket_pass, _ = TicketPass.objects.get_or_create(
            order_id=order_id, tier_id=tier_id,
            defaults={'event_id': event_id, 'owner_id': owner_id, 'qr_token': ''},
        )
        if not ticket_pass.qr_token:
            ticket_pass.qr_token = signing.dumps({'p': ticket_pass.pk, 'e': event_id}, salt=PASS_QR_SALT)
            ticket_pass.save(update_fields=['qr_token'])
        Ticket.objects.filter(order_id=order_id, tier_id=tier_id, ticket_pass__isnull=True).update(
            ticket_pass=ticket_pass,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0002_review3'),
    ]

    operations = [
        # Reversing leaves the passes in place; removing 0002 drops them.
        migrations.RunPython(create_passes, migrations.RunPython.noop),
    ]
