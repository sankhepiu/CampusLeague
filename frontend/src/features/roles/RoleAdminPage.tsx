import { useState, type FormEvent } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { ROLES, ROLE_LABELS, type Role } from '../../core/config/roles';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { membersApi } from '../members/api';
import { adminApi } from '../admin/api';
import { rolesApi } from './api';
import type { RoleInvite } from './types';
import styles from './RoleAdminPage.module.scss';

const NOMINATE_ROLES = ROLES.filter((r) => r !== 'member');

function inviteErrorMessage(err: ApiError): string {
  if (err.code === 'self_assignment') return 'You cannot nominate yourself.';
  if (err.code === 'invite_pending') return 'This person already has a pending invite for that role.';
  if (err.code === 'role_already_held') return 'This person already holds that role.';
  return err.message;
}

export function RoleAdminPage() {
  const members = useAsync(() => membersApi.list({}), []);
  const invites = useAsync(() => rolesApi.listInvites({ status: 'pending' }), []);
  const assignments = useAsync(() => adminApi.listRoles(), []);

  const [userId, setUserId] = useState('');
  const [role, setRole] = useState<Role>('event_manager');
  const [termStart, setTermStart] = useState('');
  const [termEnd, setTermEnd] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  const membersById = new Map((members.data ?? []).map((m) => [m.id, m]));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    if (termStart && termEnd && termEnd < termStart) {
      setFieldErrors({ termEnd: 'Term end cannot be before term start.' });
      return;
    }
    setSubmitting(true);
    setSavedOnce(false);
    try {
      await rolesApi.create({ user: Number(userId), role, termStart: termStart || undefined, termEnd: termEnd || undefined });
      setSavedOnce(true);
      setUserId('');
      invites.reload();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.errors && apiErr.errors.length > 0) {
        const perField: Record<string, string> = {};
        for (const fe of apiErr.errors) perField[fe.field] = fe.message;
        setFieldErrors(perField);
      } else if (apiErr.field) {
        setFieldErrors({ [apiErr.field]: inviteErrorMessage(apiErr) });
      } else {
        setGeneralError(inviteErrorMessage(apiErr));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const revoke = async (invite: RoleInvite) => {
    try {
      await rolesApi.revoke(invite.id);
      invites.reload();
    } catch (err) {
      setGeneralError((err as ApiError).message);
    }
  };

  const [endError, setEndError] = useState<string | null>(null);
  const endRole = async (assignmentId: number) => {
    setEndError(null);
    try {
      await rolesApi.endAssignment(assignmentId);
      assignments.reload();
    } catch (err) {
      const apiErr = err as ApiError;
      setEndError(apiErr.code === 'last_president' ? 'The club must always keep at least one current president — nominate a replacement first.' : apiErr.message);
    }
  };

  return (
    <PageShell title="Roles">
      <Panel accent={accentVarForFeature('roleAdmin')} className={styles.section}>
        <h2 className={styles.sectionTitle}>Invite to Role</h2>
        {savedOnce && <p className={styles.successNote}>Invite sent.</p>}
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submit} noValidate>
          <div className={styles.formRow}>
            <SelectInput
              label="Nominee"
              required
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              options={[{ value: '', label: 'Choose…' }, ...(members.data ?? []).map((m) => ({ value: String(m.id), label: `${m.name} (${m.email})` }))]}
              error={fieldErrors.user}
            />
            <SelectInput label="Role" value={role} onChange={(e) => setRole(e.target.value as Role)} options={NOMINATE_ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))} error={fieldErrors.role} />
            <TextInput label="Term Start (optional)" type="date" value={termStart} onChange={(e) => setTermStart(e.target.value)} error={fieldErrors.term_start} />
            <TextInput label="Term End (optional)" type="date" value={termEnd} onChange={(e) => setTermEnd(e.target.value)} error={fieldErrors.term_end ?? fieldErrors.termEnd} />
          </div>
          <button type="submit" className={styles.button} disabled={submitting || !userId}>
            {submitting ? <Spinner size={16} label="Sending" /> : 'Invite to Role'}
          </button>
        </form>
      </Panel>

      <h2 className={styles.sectionTitle}>Pending Invites</h2>
      {invites.status === 'loading' && <Spinner label="Loading invites…" />}
      {invites.status === 'error' && <ErrorBox error={invites.error!} onRetry={invites.reload} />}
      {invites.status === 'success' && invites.data.results.length === 0 && (
        <Panel className={styles.section}>
          <EmptyState icon="badge" title="No pending invites" />
        </Panel>
      )}
      {invites.status === 'success' && invites.data.results.length > 0 && (
        <div className={styles.list}>
          {invites.data.results.map((invite) => (
            <Panel key={invite.id} accent={accentVarForFeature('roleAdmin')}>
              <div className={styles.row}>
                <div>
                  <h3 className={styles.code}>
                    {invite.user.name} → {ROLE_LABELS[invite.role]}
                  </h3>
                  <p className={styles.meta}>
                    {invite.termStart} to {invite.termEnd} · expires {formatDateTime(invite.expiresAt)}
                  </p>
                </div>
                <StatusBadge variant="warning">Pending</StatusBadge>
              </div>
              <button type="button" className={styles.smallButtonDanger} onClick={() => revoke(invite)}>
                Revoke
              </button>
            </Panel>
          ))}
        </div>
      )}

      <h2 className={styles.sectionTitle}>Current Role Holders</h2>
      {endError && <ErrorBox error={endError} />}
      {assignments.status === 'loading' && <Spinner label="Loading role holders…" />}
      {assignments.status === 'error' && <ErrorBox error={assignments.error!} onRetry={assignments.reload} />}
      {assignments.status === 'success' && (
        <div className={styles.list}>
          {assignments.data.results.map((a) => (
            <Panel key={a.id} accent={accentVarForFeature('roleAdmin')}>
              <div className={styles.row}>
                <div>
                  <h3 className={styles.code}>
                    {membersById.get(a.user)?.name ?? `#${a.user}`} — {ROLE_LABELS[a.role]}
                  </h3>
                  <p className={styles.meta}>
                    {a.termStart} to {a.termEnd}
                  </p>
                </div>
                <button type="button" className={styles.smallButtonDanger} onClick={() => endRole(a.id)}>
                  End Role
                </button>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </PageShell>
  );
}
