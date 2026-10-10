import { useEffect, useState } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { DataTable, type DataTableColumn } from '../../components/DataTable/DataTable';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import { useAsync } from '../../core/hooks/useAsync';
import { membersApi, type MemberSummary } from './api';
import type { MembershipStatus } from '../auth/types';
import styles from './MembersPage.module.scss';

const STATUS_OPTIONS: { value: MembershipStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'active', label: 'Active' },
  { value: 'lapsed', label: 'Lapsed' },
  { value: 'none', label: 'No membership' },
];

const STATUS_VARIANT: Record<MembershipStatus, StatusBadgeVariant> = {
  active: 'success',
  lapsed: 'danger',
  none: 'neutral',
};

const COLUMNS: DataTableColumn<MemberSummary>[] = [
  { key: 'name', header: 'Name', render: (m) => m.name },
  { key: 'email', header: 'Email', render: (m) => m.email },
  { key: 'collegeId', header: 'College ID', render: (m) => m.collegeId },
  { key: 'roles', header: 'Roles', render: (m) => (m.roles.length > 0 ? m.roles.join(', ') : '—') },
  {
    key: 'status',
    header: 'Membership',
    render: (m) => <StatusBadge variant={STATUS_VARIANT[m.membershipStatus]}>{m.membershipStatus}</StatusBadge>,
  },
];

/** Staff-only list (R6) — route is already gated to president/treasurer/
 * event_manager via FEATURE_ACCESS.members, so no role check needed here. */
export function MembersPage() {
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<MembershipStatus | ''>('');

  useEffect(() => {
    const timeout = setTimeout(() => setSearch(searchInput), 250);
    return () => clearTimeout(timeout);
  }, [searchInput]);

  const { status: loadStatus, data, error, reload } = useAsync(
    () => membersApi.list({ status: status || undefined, search: search || undefined }),
    [status, search],
  );

  return (
    <PageShell title="Members">
      <div className={styles.filters}>
        <TextInput label="Search" placeholder="Name, email or college ID" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
        <SelectInput
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value as MembershipStatus | '')}
          options={STATUS_OPTIONS}
        />
      </div>

      <DataTable
        columns={COLUMNS}
        rows={data ?? []}
        rowKey={(m) => String(m.id)}
        isLoading={loadStatus === 'loading'}
        error={error}
        onRetry={reload}
        emptyMessage="No members match these filters."
      />
    </PageShell>
  );
}
