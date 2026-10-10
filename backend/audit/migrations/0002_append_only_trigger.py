from django.db import migrations

# Plan: the audit log is append-only. Enforced in PostgreSQL so it holds for
# every code path, the admin, and a database shell.
CREATE = """
CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auditlog_append_only
    BEFORE UPDATE OR DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
"""

DROP = """
DROP TRIGGER auditlog_append_only ON audit_auditlog;
DROP FUNCTION audit_log_append_only();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('audit', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(CREATE, DROP),
    ]
