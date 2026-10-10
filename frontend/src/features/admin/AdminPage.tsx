import { useState, type FormEvent } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { DataTable, type DataTableColumn } from '../../components/DataTable/DataTable';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { ROLES, ROLE_LABELS, type Role } from '../../core/config/roles';
import { membersApi } from '../members/api';
import { adminApi } from './api';
import type { AuditLogItem } from './types';
import styles from './AdminPage.module.scss';

export function AdminPage() {
  return (
    <PageShell title="Admin">
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Role Assignments</h2>
        <RoleAssignments />
      </div>
      <div className={styles.section}>
        <h2 className={styles.sectionTitle}>Audit Log</h2>
        <AuditLog />
      </div>
    </PageShell>
  );
}

function RoleAssignments() {
  const members = useAsync(() => membersApi.list({}), []);
  const { status, data, error, reload } = useAsync(() => adminApi.listRoles(), []);

  const [userId, setUserId] = useState('');
  const [role, setRole] = useState<Role>('event_manager');
  const [termStart, setTermStart] = useState('');
  const [termEnd, setTermEnd] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  const membersById = new Map((members.data ?? []).map((m) => [m.id, m.name]));
  const roleRows = data?.results ?? [];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    setSubmitting(true);
    try {
      await adminApi.assignRole({ user: Number(userId), role, termStart, termEnd });
      setSavedOnce(true);
      setUserId('');
      setTermStart('');
      setTermEnd('');
      reload();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.field) setFieldErrors({ [apiErr.field]: apiErr.message });
      else setGeneralError(apiErr.message);
    } finally {
      setSubmitting(false);
    }
  };

  const columns: DataTableColumn<(typeof roleRows)[number]>[] = [
    { key: 'user', header: 'User', render: (r) => membersById.get(r.user) ?? `#${r.user}` },
    { key: 'role', header: 'Role', render: (r) => ROLE_LABELS[r.role] },
    { key: 'start', header: 'Term Start', render: (r) => r.termStart },
    { key: 'end', header: 'Term End', render: (r) => r.termEnd },
  ];

  return (
    <Panel accent={accentVarForFeature('admin')}>
      {savedOnce && <p className={styles.successNote}>Role assigned.</p>}
      {generalError && <ErrorBox error={generalError} />}
      <form onSubmit={submit} noValidate>
        <div className={styles.formRow}>
          <SelectInput
            label="User"
            required
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            options={[{ value: '', label: 'Choose…' }, ...(members.data ?? []).map((m) => ({ value: String(m.id), label: `${m.name} (${m.email})` }))]}
            error={fieldErrors.user}
          />
          <SelectInput label="Role" value={role} onChange={(e) => setRole(e.target.value as Role)} options={ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))} error={fieldErrors.role} />
          <TextInput label="Term Start" type="date" required value={termStart} onChange={(e) => setTermStart(e.target.value)} error={fieldErrors.term_start} />
          <TextInput label="Term End" type="date" required value={termEnd} onChange={(e) => setTermEnd(e.target.value)} error={fieldErrors.term_end} />
        </div>
        <button type="submit" className={styles.button} disabled={submitting || !userId || !termStart || !termEnd}>
          {submitting ? <Spinner size={16} label="Assigning" /> : 'Assign Role'}
        </button>
      </form>

      <div className={styles.readable} style={{ marginTop: '1.5rem' }}>
        <DataTable columns={columns} rows={roleRows} rowKey={(r) => String(r.id)} isLoading={status === 'loading'} error={status === 'error' ? error : null} onRetry={reload} emptyMessage="No role assignments yet." />
      </div>
    </Panel>
  );
}

const ACTION_OPTIONS = [
  { value: '', label: 'All actions' },
  { value: 'role.assigned', label: 'role.assigned' },
  { value: 'expense.approved', label: 'expense.approved' },
  { value: 'stock.restocked', label: 'stock.restocked' },
  { value: 'savefile.updated', label: 'savefile.updated' },
  { value: 'savefile.created', label: 'savefile.created' },
];

function AuditLog() {
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => adminApi.listAuditLog({ action: action || undefined }, page), [action, page]);

  const columns: DataTableColumn<AuditLogItem>[] = [
    { key: 'at', header: 'When', render: (a) => new Date(a.at).toLocaleString('en-IN') },
    { key: 'actor', header: 'Actor', render: (a) => a.actor?.name ?? 'System' },
    { key: 'action', header: 'Action', render: (a) => a.action },
    { key: 'object', header: 'Object', render: (a) => `${a.objectType} #${a.objectId}` },
    {
      key: 'diff',
      header: 'Before → After',
      wrap: true,
      render: (a) => (
        <div className={styles.diff}>
          {a.before && <div className={styles.diffBefore}>− {JSON.stringify(a.before)}</div>}
          {a.after && <div className={styles.diffAfter}>+ {JSON.stringify(a.after)}</div>}
        </div>
      ),
    },
  ];

  return (
    <Panel accent={accentVarForFeature('admin')}>
      <SelectInput
        label="Action"
        className={styles.filterRow}
        value={action}
        onChange={(e) => {
          setAction(e.target.value);
          setPage(1);
        }}
        options={ACTION_OPTIONS}
      />
      <div className={styles.readable}>
        <DataTable columns={columns} rows={data?.results ?? []} rowKey={(a) => String(a.id)} isLoading={status === 'loading'} error={status === 'error' ? error : null} onRetry={reload} emptyMessage="No audit log entries match this filter." />
      </div>
      {status === 'success' && (
        <div className={styles.pagination}>
          <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p - 1)} disabled={!data.previous}>
            ← Previous
          </button>
          <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p + 1)} disabled={!data.next}>
            Next →
          </button>
        </div>
      )}
    </Panel>
  );
}
