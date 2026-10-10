from django.db import migrations

# Plan, ledger design, "Accounts (starter list)".
STARTER_ACCOUNTS = [
    ('1000', 'Cash and bank', 'asset'),
    ('2000', 'Reimbursements payable', 'liability'),
    ('4000', 'Membership dues revenue', 'revenue'),
    ('4100', 'Ticket revenue', 'revenue'),
    ('4200', 'Merchandise revenue', 'revenue'),
    ('4300', 'Fundraiser revenue', 'revenue'),
    ('5000', 'Event expenses', 'expense'),
    ('5100', 'Fundraiser expenses', 'expense'),
    ('5200', 'General club expenses', 'expense'),
]


def create_starter_accounts(apps, schema_editor):
    LedgerAccount = apps.get_model('finance', 'LedgerAccount')
    for code, name, type_ in STARTER_ACCOUNTS:
        LedgerAccount.objects.get_or_create(code=code, defaults={'name': name, 'type': type_})


def remove_starter_accounts(apps, schema_editor):
    LedgerAccount = apps.get_model('finance', 'LedgerAccount')
    LedgerAccount.objects.filter(code__in=[code for code, _, _ in STARTER_ACCOUNTS]).delete()


# These rules live in PostgreSQL, so they hold no matter which code path (or
# person with a database shell) touches the tables.
CREATE_TRIGGERS = """
-- 1. Append-only. Plan: "Never update or delete a ledger entry."
CREATE FUNCTION finance_ledger_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger is append-only: % on % is not allowed', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ledgerentry_append_only
    BEFORE UPDATE OR DELETE ON finance_ledgerentry
    FOR EACH ROW EXECUTE FUNCTION finance_ledger_append_only();

CREATE TRIGGER ledgerline_append_only
    BEFORE UPDATE OR DELETE ON finance_ledgerline
    FOR EACH ROW EXECUTE FUNCTION finance_ledger_append_only();

-- 2. Balanced. Plan: "Each entry's debits must equal its credits."
-- A CHECK constraint sees one row at a time, so it cannot compare the lines
-- of an entry. This trigger is DEFERRED: it runs at COMMIT, once all of the
-- entry's lines have been inserted, and aborts the transaction if the entry
-- has no lines or its debits and credits differ.
CREATE FUNCTION finance_ledger_entry_balanced() RETURNS trigger AS $$
DECLARE
    checked_entry bigint;
    total_debit bigint;
    total_credit bigint;
BEGIN
    IF TG_TABLE_NAME = 'finance_ledgerentry' THEN
        checked_entry := NEW.id;
    ELSE
        checked_entry := NEW.entry_id;
    END IF;

    SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
      INTO total_debit, total_credit
      FROM finance_ledgerline
     WHERE entry_id = checked_entry;

    IF total_debit = 0 OR total_debit <> total_credit THEN
        RAISE EXCEPTION 'ledger entry % does not balance: debits %, credits %',
            checked_entry, total_debit, total_credit
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ledgerentry_balanced
    AFTER INSERT ON finance_ledgerentry
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION finance_ledger_entry_balanced();

CREATE CONSTRAINT TRIGGER ledgerline_balanced
    AFTER INSERT ON finance_ledgerline
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION finance_ledger_entry_balanced();
"""

DROP_TRIGGERS = """
DROP TRIGGER ledgerline_balanced ON finance_ledgerline;
DROP TRIGGER ledgerentry_balanced ON finance_ledgerentry;
DROP FUNCTION finance_ledger_entry_balanced();
DROP TRIGGER ledgerline_append_only ON finance_ledgerline;
DROP TRIGGER ledgerentry_append_only ON finance_ledgerentry;
DROP FUNCTION finance_ledger_append_only();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_starter_accounts, remove_starter_accounts),
        migrations.RunSQL(CREATE_TRIGGERS, DROP_TRIGGERS),
    ]
