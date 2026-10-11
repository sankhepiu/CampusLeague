import { Link } from 'react-router-dom';
import { useState } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { DataTable, type DataTableColumn } from '../../components/DataTable/DataTable';
import { SelectInput } from '../../components/FormField/SelectInput';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { ROLE_LABELS } from '../../core/config/roles';
import { membersApi } from '../members/api';
import { adminApi } from './api';
import type { AuditLogItem } from './types';
import styles from './AdminPage.module.scss';
import { formatDateTime } from '../../core/utils/formatDateTime';

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

  const membersById = new Map((members.data ?? []).map((m) => [m.id, m.name]));
  const roleRows = data?.results ?? [];

  const columns: DataTableColumn<(typeof roleRows)[number]>[] = [
    { key: 'user', header: 'User', render: (r) => membersById.get(r.user) ?? `#${r.user}` },
    { key: 'role', header: 'Role', render: (r) => ROLE_LABELS[r.role] },
    { key: 'start', header: 'Term Start', render: (r) => r.termStart },
    { key: 'end', header: 'Term End', render: (r) => r.termEnd },
  ];

  return (
    <Panel accent={accentVarForFeature('admin')}>
      {/* A role is now offered, not imposed — nominating, the pending invite
          list and ending a term all live on the dedicated Roles page. */}
      <p className={styles.successNote}>
        <Link to="/roles">Manage role invites and terms →</Link>
      </p>
      <div className={styles.readable}>
        <DataTable columns={columns} rows={roleRows} rowKey={(r) => String(r.id)} isLoading={status === 'loading'} error={status === 'error' ? error : null} onRetry={reload} emptyMessage="No role assignments yet." />
      </div>
    </Panel>
  );
}

/** Every action the backend writes (docs/API_CONTRACT.md, "GET /audit"),
 * with a label a person can read. The value is what `?action=` takes. */
const ACTION_LABELS: Record<string, string> = {
  'role.invited': 'Role invite sent',
  'role.assigned': 'Role accepted and assigned',
  'role.invite_declined': 'Role invite declined',
  'role.invite_revoked': 'Role invite revoked',
  'role.ended': 'Role ended',
  'stock.restocked': 'Stock restocked',
  'order.refund_due': 'Order refund due',
  'expense.approved': 'Expense approved',
  'expense.rejected': 'Expense rejected',
  'expense.paid': 'Expense paid',
  'savefile.created': 'Save file created',
  'savefile.updated': 'Save file updated',
};

const ACTION_OPTIONS = [
  { value: '', label: 'All actions' },
  ...Object.entries(ACTION_LABELS).map(([value, label]) => ({ value, label: `${label} (${value})` })),
];

/** Readable label for a row; an action this build does not know yet is
 * shown as the server sent it. */
function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

function AuditLog() {
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => adminApi.listAuditLog({ action: action || undefined }, page), [action, page]);

  const columns: DataTableColumn<AuditLogItem>[] = [
    { key: 'at', header: 'When', render: (a) => formatDateTime(a.at) },
    { key: 'actor', header: 'Actor', render: (a) => a.actor?.name ?? 'System' },
    { key: 'action', header: 'Action', render: (a) => <span title={a.action}>{actionLabel(a.action)}</span> },
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
