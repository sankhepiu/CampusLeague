import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { accentVarForFeature } from '../../core/config/accents';
import { announcementsApi } from './api';
import type { Announcement, Audience } from './types';
import styles from './AnnouncementComposerPage.module.scss';

const TITLE_MAX = 200;
const AUDIENCE_OPTIONS: { value: Audience; label: string }[] = [
  { value: 'all', label: 'Everyone' },
  { value: 'members', label: 'Active members only' },
];

export function AnnouncementComposerPage() {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [audience, setAudience] = useState<Audience>('all');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);
  const [posted, setPosted] = useState<Announcement | null>(null);

  const validate = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    if (!title.trim()) errors.title = 'Title is required.';
    else if (title.length > TITLE_MAX) errors.title = `Title must be ${TITLE_MAX} characters or fewer.`;
    if (!body.trim()) errors.body = 'Body is required.';
    return errors;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    setGeneralError(null);
    if (Object.keys(errors).length > 0) return;

    setPosting(true);
    try {
      const result = await announcementsApi.create({ title: title.trim(), body, audience });
      setPosted(result);
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.errors && apiError.errors.length > 0) {
        const perField: Record<string, string> = {};
        for (const fe of apiError.errors) perField[fe.field] = fe.message;
        setFieldErrors(perField);
      } else if (apiError.field) {
        setFieldErrors({ [apiError.field]: apiError.message });
      } else {
        setGeneralError(apiError.message);
      }
    } finally {
      setPosting(false);
    }
  };

  if (posted) {
    return (
      <PageShell title="Announcement Posted">
        <Panel accent="var(--cl-green)" className={styles.successBox}>
          <p>
            <strong>Saved.</strong>
          </p>
          {posted.deliveries && (
            <>
              <div className={styles.deliveryRow}>
                <span>{posted.deliveries.recipients} recipients</span>
                <span>{posted.deliveries.sent} sent</span>
                <span>{posted.deliveries.failed} failed</span>
              </div>
              {posted.deliveries.failed > 0 && (
                <p className={styles.failedWarning}>
                  {posted.deliveries.failed} email{posted.deliveries.failed === 1 ? '' : 's'} did not go out; the server will retry.
                </p>
              )}
            </>
          )}
          <div style={{ marginTop: '1rem' }}>
            <Link to={`/announcements/${posted.id}`} className={styles.linkButton}>
              View Announcement
            </Link>
            <Link to="/announcements" className={styles.linkButton}>
              Back to Archive
            </Link>
          </div>
        </Panel>
      </PageShell>
    );
  }

  return (
    <PageShell title="New Announcement">
      <Panel accent={accentVarForFeature('announcements')}>
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submit} noValidate>
          <TextInput
            label="Title"
            required
            maxLength={TITLE_MAX}
            hint={`${title.length}/${TITLE_MAX} characters`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            error={fieldErrors.title}
          />

          <div className={styles.fieldWrap}>
            <label className={styles.label} htmlFor="announcement-body">
              Body <span style={{ color: 'var(--cl-color-danger)' }}>*</span>
            </label>
            <textarea
              id="announcement-body"
              className={styles.textarea}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              aria-invalid={!!fieldErrors.body}
            />
            {fieldErrors.body && <p className={styles.error}>{fieldErrors.body}</p>}
          </div>

          <SelectInput label="Audience" value={audience} onChange={(e) => setAudience(e.target.value as Audience)} options={AUDIENCE_OPTIONS} />

          <button type="submit" className={styles.button} disabled={posting}>
            {posting ? <Spinner size={16} label="Posting" /> : 'Post Announcement'}
          </button>
        </form>
      </Panel>
    </PageShell>
  );
}
