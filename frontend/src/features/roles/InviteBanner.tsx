import { useState } from 'react';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { ROLE_LABELS } from '../../core/config/roles';
import { rolesApi } from './api';
import type { RoleInvite } from './types';
import styles from './InviteBanner.module.scss';

export function InviteBanner() {
  const { user } = useAuth();
  const invites = useAsync(() => rolesApi.listInvites({ status: 'pending' }), [], { enabled: !!user });

  if (!user || invites.status !== 'success') return null;
  // A president's GET /roles/invites returns every pending invite (needed
  // for the admin list on the Roles page) — the banner must only surface
  // ones actually addressed to the person viewing it.
  const mine = invites.data.results.filter((i) => i.user.id === user.id);
  if (mine.length === 0) return null;

  return (
    <div className={styles.stack}>
      {mine.map((invite) => (
        <InviteRow key={invite.id} invite={invite} onAnswered={invites.reload} />
      ))}
    </div>
  );
}

function InviteRow({ invite, onAnswered }: { invite: RoleInvite; onAnswered: () => void }) {
  const { refreshUser } = useAuth();
  const [busy, setBusy] = useState<'accept' | 'decline' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const respond = async (decision: 'accept' | 'decline') => {
    setBusy(decision);
    setError(null);
    try {
      if (decision === 'accept') {
        await rolesApi.accept(invite.id);
        await refreshUser();
      } else {
        await rolesApi.decline(invite.id);
      }
      onAnswered();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.code === 'invite_not_pending' ? 'This invite is no longer pending — it may have expired or been revoked.' : apiErr.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={styles.banner} role="status">
      <span>
        You've been invited as <strong>{ROLE_LABELS[invite.role]}</strong> by {invite.invitedBy.name}.
      </span>
      {error && <ErrorBox error={error} />}
      <div className={styles.actions}>
        <button type="button" className={styles.accept} onClick={() => respond('accept')} disabled={busy !== null}>
          {busy === 'accept' ? <Spinner size={14} label="Accepting" /> : 'Accept'}
        </button>
        <button type="button" className={styles.decline} onClick={() => respond('decline')} disabled={busy !== null}>
          {busy === 'decline' ? <Spinner size={14} label="Declining" /> : 'Decline'}
        </button>
      </div>
    </div>
  );
}
