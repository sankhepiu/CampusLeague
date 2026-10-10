import { useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { ProgressBar } from '../../components/ProgressBar/ProgressBar';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { volunteeringApi } from './api';
import { listAssignableUsers, type AssignableUser } from './listAssignableUsers';
import type { Task, TaskStatus } from './types';
import styles from './FundraiserDetailPage.module.scss';

const STATUS_LABELS: { value: TaskStatus; label: string }[] = [
  { value: 'todo', label: 'To Do' },
  { value: 'doing', label: 'Doing' },
  { value: 'done', label: 'Done' },
];

export function FundraiserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const fundraiserId = Number(id);
  const { user, hasRole } = useAuth();
  const canManage = hasRole('president', 'volunteer_coordinator');

  const { status, data: fundraiser, error, reload } = useAsync(() => volunteeringApi.getFundraiser(fundraiserId), [fundraiserId]);
  const assignable = useAsync(() => listAssignableUsers(), [], { enabled: canManage });

  const [showAddTask, setShowAddTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDue, setTaskDue] = useState('');
  const [addingTask, setAddingTask] = useState(false);
  const [addTaskError, setAddTaskError] = useState<string | null>(null);

  const submitTask = async (e: FormEvent) => {
    e.preventDefault();
    setAddTaskError(null);
    setAddingTask(true);
    try {
      await volunteeringApi.createTask({ fundraiser: fundraiserId, title: taskTitle.trim(), dueDate: taskDue || null });
      setTaskTitle('');
      setTaskDue('');
      setShowAddTask(false);
      reload();
    } catch (err) {
      setAddTaskError((err as ApiError).message);
    } finally {
      setAddingTask(false);
    }
  };

  if (status === 'loading') return <Spinner fullPage label="Loading fundraiser…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!fundraiser) return null;

  const columns: { status: TaskStatus; label: string }[] = [
    { status: 'todo', label: 'To Do' },
    { status: 'doing', label: 'Doing' },
    { status: 'done', label: 'Done' },
  ];

  return (
    <PageShell title={fundraiser.title}>
      <div className={styles.header}>
        <p className={styles.meta}>
          {fundraiser.startsOn} to {fundraiser.endsOn}
        </p>
        {canManage && (
          <Link to={`/volunteering/${fundraiser.id}/edit`} className={styles.editLink}>
            Edit Fundraiser
          </Link>
        )}
      </div>

      <Panel accent={accentVarForFeature('volunteering')} className={styles.goalPanel}>
        <ProgressBar
          percent={fundraiser.progress.raisedPct}
          onTrack={fundraiser.progress.onTrack}
          label={
            <>
              <Money paise={fundraiser.progress.raisedAmount} /> of <Money paise={fundraiser.progress.goalAmount} /> ({fundraiser.progress.raisedPct}%)
            </>
          }
        />
      </Panel>

      {canManage && (
        <button type="button" className={styles.addTaskButton} onClick={() => setShowAddTask((v) => !v)}>
          {showAddTask ? 'Cancel' : '+ Add Task'}
        </button>
      )}

      {showAddTask && (
        <Panel className={styles.goalPanel}>
          {addTaskError && <ErrorBox error={addTaskError} />}
          <form onSubmit={submitTask} noValidate style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <TextInput label="Title" required value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} />
            <TextInput label="Due Date" type="date" value={taskDue} onChange={(e) => setTaskDue(e.target.value)} />
            <button type="submit" className={styles.addTaskButton} style={{ marginBottom: '1.1rem' }} disabled={addingTask || !taskTitle.trim()}>
              {addingTask ? <Spinner size={16} label="Adding" /> : 'Add'}
            </button>
          </form>
        </Panel>
      )}

      <div className={styles.columns}>
        {columns.map((col) => (
          <div key={col.status}>
            <h3 className={styles.columnTitle}>{col.label}</h3>
            {fundraiser.tasks
              .filter((t) => t.status === col.status)
              .map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  currentUserId={user?.id ?? null}
                  canManage={canManage}
                  assignable={assignable.data ?? []}
                  onChanged={reload}
                />
              ))}
            {fundraiser.tasks.filter((t) => t.status === col.status).length === 0 && <p className={styles.meta}>Nothing here.</p>}
          </div>
        ))}
      </div>
    </PageShell>
  );
}

function TaskCard({
  task,
  currentUserId,
  canManage,
  assignable,
  onChanged,
}: {
  task: Task;
  currentUserId: number | null;
  canManage: boolean;
  assignable: AssignableUser[];
  onChanged: () => void;
}) {
  const isAssignee = currentUserId !== null && task.assignees.some((a) => a.id === currentUserId);
  const canSetStatus = canManage || isAssignee;

  const [statusError, setStatusError] = useState<string | null>(null);
  const [settingStatus, setSettingStatus] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [assignUserId, setAssignUserId] = useState('');
  const [assignNote, setAssignNote] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);

  const changeStatus = async (next: TaskStatus) => {
    if (next === task.status) return;
    setStatusError(null);
    setSettingStatus(true);
    try {
      await volunteeringApi.setTaskStatus(task.id, next);
      onChanged();
    } catch (err) {
      setStatusError((err as ApiError).message);
    } finally {
      setSettingStatus(false);
    }
  };

  const submitAssign = async (e: FormEvent) => {
    e.preventDefault();
    if (!assignUserId) return;
    setAssignError(null);
    setAssigning(true);
    try {
      await volunteeringApi.assignTask(task.id, { user: Number(assignUserId), roleNote: assignNote.trim() });
      setShowAssign(false);
      setAssignUserId('');
      setAssignNote('');
      onChanged();
    } catch (err) {
      setAssignError((err as ApiError).message);
    } finally {
      setAssigning(false);
    }
  };

  return (
    <Panel className={styles.taskCard} accent={accentVarForFeature('volunteering')}>
      <h4 className={styles.taskTitle}>{task.title}</h4>
      {task.dueDate && <p className={styles.taskDue}>Due {task.dueDate}</p>}

      {task.assignees.length > 0 && (
        <ul className={styles.assigneeList}>
          {task.assignees.map((a) => (
            <li key={a.id} className={styles.assigneeRow}>
              {a.name}
              {a.roleNote ? ` — ${a.roleNote}` : ''}
            </li>
          ))}
        </ul>
      )}

      {statusError && <ErrorBox error={statusError} />}
      {canSetStatus && (
        <div className={styles.statusRow}>
          {STATUS_LABELS.map((s) => (
            <button
              key={s.value}
              type="button"
              className={`${styles.statusButton} ${task.status === s.value ? styles.statusButtonActive : ''}`}
              disabled={settingStatus}
              onClick={() => changeStatus(s.value)}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      {canManage && (
        <>
          <button type="button" className={styles.assignToggle} onClick={() => setShowAssign((v) => !v)}>
            {showAssign ? 'Cancel' : '+ Assign'}
          </button>
          {showAssign && (
            <form onSubmit={submitAssign} className={styles.assignForm}>
              {assignError && <ErrorBox error={assignError} />}
              <SelectInput
                label="Person"
                value={assignUserId}
                onChange={(e) => setAssignUserId(e.target.value)}
                options={[{ value: '', label: 'Choose…' }, ...assignable.map((a) => ({ value: String(a.id), label: a.name }))]}
              />
              <TextInput label="Role note" value={assignNote} onChange={(e) => setAssignNote(e.target.value)} />
              <button type="submit" className={styles.addTaskButton} disabled={assigning || !assignUserId}>
                {assigning ? <Spinner size={16} label="Assigning" /> : 'Assign'}
              </button>
            </form>
          )}
        </>
      )}
    </Panel>
  );
}
