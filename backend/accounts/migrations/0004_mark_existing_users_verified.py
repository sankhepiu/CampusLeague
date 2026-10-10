from django.db import migrations


def mark_existing_verified(apps, schema_editor):
    # Accounts created before email verification existed keep working: they
    # are treated as verified. Only accounts created from now on start
    # unverified.
    User = apps.get_model('accounts', 'User')
    User.objects.update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_email_verified_emailverificationcode'),
    ]

    operations = [
        # Reversing leaves the flags as they are; nothing to undo.
        migrations.RunPython(mark_existing_verified, migrations.RunPython.noop),
    ]
