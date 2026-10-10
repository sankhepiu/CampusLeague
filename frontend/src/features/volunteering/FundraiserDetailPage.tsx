import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
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

const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: 'todo', label: 'To Do' },
  { status: 'doing', label: 'Doing' },
  { status: 'done', label: 'Done' },
];

/** The task drag-data mime type — plain text is the most compatible carrier
 * across browsers for a same-page drag (no file/URL semantics needed). */
const DRAG_MIME = 'text/plain';

function isAssigneeOf(task: Task, userId: number | null): boolean {
  return userId !== null && task.assignees.some((a) => a.id === userId);
}

/** The server's 403 on a status move is always `permission_denied`, but its
 * message is backend-generic; the brief wants this specific, friendlier
 * wording for the move case. */
function moveErrorMessage(err: ApiError): string {
  if (err.code === 'permission_denied') return 'Only assignees or the coordinator can move this.';
  return err.message;
}

export function FundraiserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const fundraiserId = Number(id);
  const { user, hasRole } = useAuth();
  const canManage = hasRole('president', 'volunteer_coordinator');

  const { status, data: fundraiser, error, reload } = useAsync(() => volunteeringApi.getFundraiser(fundraiserId), [fundraiserId]);
  const assignable = useAsync(() => listAssignableUsers(), [], { enabled: canManage });

  // Local, optimistically-mutable mirror of the server's tasks — kept in
  // sync whenever a fresh fundraiser loads, but drag/drop and the move menu
  // update this directly so the board responds instantly instead of
  // waiting on a round trip (and the whole page re-fetching would flash
  // the full-page spinner on every single move).
  const [tasks, setTasks] = useState<Task[]>([]);
  useEffect(() => {
    if (fundraiser) setTasks(fundraiser.tasks);
  }, [fundraiser]);

  const [draggingTaskId, setDraggingTaskId] = useState<number | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const [moveError, setMoveError] = useState<{ taskId: number; message: string } | null>(null);

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

  const moveTask = async (taskId: number, nextStatus: TaskStatus) => {
    const task = tasks.find((t) => t.id === taskId);
    if (!task || task.status === nextStatus) return;
    const prevStatus = task.status;

    setMoveError(null);
    setTasks((ts) => ts.map((t) => (t.id === taskId ? { ...t, status: nextStatus } : t)));
    try {
      await volunteeringApi.setTaskStatus(taskId, nextStatus);
    } catch (err) {
      setTasks((ts) => ts.map((t) => (t.id === taskId ? { ...t, status: prevStatus } : t)));
      setMoveError({ taskId, message: moveErrorMessage(err as ApiError) });
    }
  };

  if (status === 'loading') return <Spinner fullPage label="Loading fundraiser…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!fundraiser) return null;

  const currentUserId = user?.id ?? null;
  const userCanDragAny = canManage || tasks.some((t) => isAssigneeOf(t, currentUserId));
  const tasksDone = tasks.filter((t) => t.status === 'done').length;
  const tasksTotal = tasks.length;

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

      <Panel accent={accentVarForFeature('volunteering')} className={styles.goalPanel}>
        <ProgressBar percent={tasksTotal > 0 ? (tasksDone / tasksTotal) * 100 : 0} label={`${tasksDone}/${tasksTotal} tasks done`} />
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

      {!userCanDragAny && <p className={styles.viewOnlyNote}>View only — you don't have any tasks to move on this board.</p>}

      <div className={styles.columns}>
        {COLUMNS.map((col) => {
          const colTasks = tasks.filter((t) => t.status === col.status);
          return (
            <div
              key={col.status}
              className={`${styles.column} ${dragOverColumn === col.status ? styles.columnDragOver : ''}`}
              onDragOver={(e: DragEvent<HTMLDivElement>) => {
                if (draggingTaskId === null) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                setDragOverColumn(col.status);
              }}
              onDragLeave={(e: DragEvent<HTMLDivElement>) => {
                if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
                setDragOverColumn((cur) => (cur === col.status ? null : cur));
              }}
              onDrop={(e: DragEvent<HTMLDivElement>) => {
                e.preventDefault();
                setDragOverColumn(null);
                const taskId = Number(e.dataTransfer.getData(DRAG_MIME));
                if (Number.isFinite(taskId)) void moveTask(taskId, col.status);
              }}
            >
              <h3 className={styles.columnTitle}>
                {col.label} <span className={styles.columnCount}>({colTasks.length})</span>
              </h3>
              {colTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  canManage={canManage}
                  canDrag={canManage || isAssigneeOf(task, currentUserId)}
                  assignable={assignable.data ?? []}
                  moveError={moveError?.taskId === task.id ? moveError.message : null}
                  onMove={moveTask}
                  onDragStart={() => setDraggingTaskId(task.id)}
                  onDragEnd={() => {
                    setDraggingTaskId(null);
                    setDragOverColumn(null);
                  }}
                  onAssigned={reload}
                />
              ))}
              {colTasks.length === 0 && <p className={styles.meta}>Nothing here.</p>}
            </div>
          );
        })}
      </div>
    </PageShell>
  );
}

function TaskCard({
  task,
  canManage,
  canDrag,
  assignable,
  moveError,
  onMove,
  onDragStart,
  onDragEnd,
  onAssigned,
}: {
  task: Task;
  canManage: boolean;
  canDrag: boolean;
  assignable: AssignableUser[];
  moveError: string | null;
  onMove: (taskId: number, next: TaskStatus) => void;
  onDragStart: () => void;
  onDragEnd: () => void;
  onAssigned: () => void;
}) {
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [assignUserId, setAssignUserId] = useState('');
  const [assignNote, setAssignNote] = useState('');
  const [assigning, setAssigning] = useState(false);
  const [assignError, setAssignError] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showMoveMenu) return;
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowMoveMenu(false);
    };
    document.addEventListener('click', onClickOutside);
    return () => document.removeEventListener('click', onClickOutside);
  }, [showMoveMenu]);

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
      onAssigned();
    } catch (err) {
      setAssignError((err as ApiError).message);
    } finally {
      setAssigning(false);
    }
  };

  const otherColumns = COLUMNS.filter((c) => c.status !== task.status);

  return (
    <Panel
      className={styles.taskCard}
      accent={accentVarForFeature('volunteering')}
      draggable={canDrag}
      onDragStart={(e: DragEvent<HTMLDivElement>) => {
        e.dataTransfer.setData(DRAG_MIME, String(task.id));
        e.dataTransfer.effectAllowed = 'move';
        onDragStart();
      }}
      onDragEnd={onDragEnd}
    >
      <div className={styles.taskHeader}>
        {canDrag && (
          <span className={styles.dragHandle} aria-hidden="true" title="Drag to move">
            ⠿
          </span>
        )}
        <h4 className={styles.taskTitle}>{task.title}</h4>
      </div>
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

      {moveError && <ErrorBox error={moveError} />}

      {canDrag && (
        <div className={styles.moveMenu} ref={menuRef}>
          <button type="button" className={styles.moveToggle} onClick={() => setShowMoveMenu((v) => !v)} aria-haspopup="menu" aria-expanded={showMoveMenu}>
            Move to ▸
          </button>
          {showMoveMenu && (
            <div className={styles.moveList} role="menu">
              {otherColumns.map((c) => (
                <button
                  key={c.status}
                  type="button"
                  role="menuitem"
                  className={styles.moveItem}
                  onClick={() => {
                    setShowMoveMenu(false);
                    onMove(task.id, c.status);
                  }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
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
