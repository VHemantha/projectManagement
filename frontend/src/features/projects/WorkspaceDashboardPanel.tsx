import { format, parseISO } from 'date-fns'
import { CalendarClock, ChevronsLeft, ChevronsRight, Clock, FileText, Pencil, StickyNote, X } from 'lucide-react'
import { useEffect, useState, useSyncExternalStore } from 'react'

import styles from './WorkspaceDashboardPanel.module.css'
import {
  budgetStatus,
  countdownText,
  DEADLINE_LABELS,
  deadlineStatus,
  formatHours,
} from './workspaceDashboard'
import { extractErrorMessage } from '@/api/errors'
import { type UpdateProjectPayload, useUpdateProject } from '@/api/projects'
import type { ProjectDetail } from '@/api/types'
import { Tooltip } from '@/design-system'
import { usePanel } from '@/store/sidebarStore'

/** Below this width the panel starts collapsed and opens over the board instead of beside it. */
const NARROW_QUERY = '(max-width: 1024px)'

function useIsNarrow(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia?.(NARROW_QUERY)
      mq?.addEventListener('change', onChange)
      return () => mq?.removeEventListener('change', onChange)
    },
    () => window.matchMedia?.(NARROW_QUERY).matches ?? false,
  )
}

/** The workspace's time, deadline, description and notes, beside its Kanban board. */
export function WorkspaceDashboardPanel({ project }: { project: ProjectDetail }) {
  const stored = usePanel('workspaceDashboard')
  const narrow = useIsNarrow()
  // Wide screens remember the choice; narrow ones start collapsed each time.
  const [narrowOpen, setNarrowOpen] = useState(false)
  const open = narrow ? narrowOpen : stored.open
  const setOpen = (value: boolean) => (narrow ? setNarrowOpen(value) : stored.setOpen(value))

  const update = useUpdateProject(project.key)
  const save = (patch: UpdateProjectPayload) => update.mutateAsync(patch)

  const budget = budgetStatus(project.actual_hours, project.budgeted_hours)
  const deadline = deadlineStatus(project.deadline)

  if (!open) {
    return (
      <aside className={styles.rail} aria-label="Workspace dashboard">
        <Tooltip label="Show dashboard" side="left">
          <button type="button" className={styles.railToggle} onClick={() => setOpen(true)} aria-label="Show dashboard">
            <ChevronsLeft size={18} />
          </button>
        </Tooltip>
        <RailIcon label={timeSummary(project)} tone={budget} onClick={() => setOpen(true)} icon={<Clock size={18} />} />
        <RailIcon
          label={project.deadline ? `Deadline: ${DEADLINE_LABELS[deadline.status as 'on_track']}` : 'No deadline'}
          tone={deadline.status}
          onClick={() => setOpen(true)}
          icon={<CalendarClock size={18} />}
        />
        <RailIcon label="Description" onClick={() => setOpen(true)} icon={<FileText size={18} />} />
        <RailIcon label="Special notes" onClick={() => setOpen(true)} icon={<StickyNote size={18} />} />
      </aside>
    )
  }

  return (
    <>
      {narrow && <div className={styles.backdrop} onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className={`${styles.panel} ${narrow ? styles.overlay : ''}`} aria-label="Workspace dashboard">
        <div className={styles.panelHeader}>
          <h2 className={styles.panelTitle}>Dashboard</h2>
          <Tooltip label="Hide dashboard" side="left">
            <button type="button" className={styles.iconButton} onClick={() => setOpen(false)} aria-label="Hide dashboard">
              <ChevronsRight size={18} />
            </button>
          </Tooltip>
        </div>

        {update.isError && (
          <div role="alert" className={styles.error}>
            {extractErrorMessage(update.error)}
          </div>
        )}

        <TimeCard project={project} canEdit={project.can_manage} onSave={save} />
        <DeadlineCard project={project} canEdit={project.can_manage} onSave={save} />

        <Card icon={<FileText size={16} />} tone="violet" title="Description">
          <AutosaveText
            id="workspace-description"
            label="Workspace description"
            value={project.description}
            canEdit={project.can_manage}
            placeholder="What this workspace is for…"
            emptyText="No description."
            onSave={(value) => save({ description: value })}
          />
        </Card>

        <Card icon={<StickyNote size={16} />} tone="orange" title="Special notes">
          <AutosaveText
            id="workspace-notes"
            label="Special notes"
            value={project.special_notes}
            canEdit={project.can_manage}
            placeholder="Anything the team should keep in mind…"
            emptyText="No special notes."
            rows={5}
            onSave={(value) => save({ special_notes: value })}
          />
        </Card>

        {!project.can_manage && (
          <p className={styles.readOnlyHint}>Only the workspace lead or an admin can edit these.</p>
        )}
      </aside>
    </>
  )
}

function timeSummary(project: ProjectDetail): string {
  const actual = formatHours(project.actual_hours)
  return project.budgeted_hours == null ? `Time: ${actual} logged` : `Time: ${actual} of ${formatHours(project.budgeted_hours)}`
}

function RailIcon({
  label,
  icon,
  tone,
  onClick,
}: {
  label: string
  icon: React.ReactNode
  tone?: string
  onClick: () => void
}) {
  return (
    <Tooltip label={label} side="left">
      <button type="button" className={styles.railButton} onClick={onClick} aria-label={label}>
        {icon}
        {tone && tone !== 'none' && <span className={styles.dot} data-tone={tone} aria-hidden="true" />}
      </button>
    </Tooltip>
  )
}

function Card({
  icon,
  tone,
  title,
  aside,
  children,
}: {
  icon: React.ReactNode
  tone: 'blue' | 'teal' | 'violet' | 'orange'
  title: string
  aside?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className={styles.card} aria-label={title}>
      <div className={styles.cardHeader}>
        <span className={styles.cardIcon} data-tone={tone} aria-hidden="true">
          {icon}
        </span>
        <h3 className={styles.cardTitle}>{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

type Save = (patch: UpdateProjectPayload) => Promise<unknown>

function TimeCard({ project, canEdit, onSave }: { project: ProjectDetail; canEdit: boolean; onSave: Save }) {
  const [editing, setEditing] = useState(false)
  const status = budgetStatus(project.actual_hours, project.budgeted_hours)
  const budget = project.budgeted_hours
  const pct = budget ? Math.min(100, (project.actual_hours / budget) * 100) : 0

  return (
    <Card
      icon={<Clock size={16} />}
      tone="blue"
      title="Time"
      aside={
        canEdit &&
        !editing && (
          <Tooltip label={budget == null ? 'Set budget' : 'Edit budget'} side="left">
            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setEditing(true)}
              aria-label={budget == null ? 'Set budget' : 'Edit budget'}
            >
              <Pencil size={14} />
            </button>
          </Tooltip>
        )
      }
    >
      <div className={styles.timeFigures}>
        <span className={styles.bigNumber} data-tone={status}>
          {formatHours(project.actual_hours)}
        </span>
        <span className={styles.subtle}>{budget == null ? 'logged' : `of ${formatHours(budget)} budgeted`}</span>
      </div>
      {budget != null && (
        <div
          className={styles.bar}
          role="meter"
          aria-label="Time used of budget"
          aria-valuemin={0}
          aria-valuemax={budget}
          aria-valuenow={project.actual_hours}
        >
          <div className={styles.barFill} data-tone={status} style={{ width: `${pct}%` }} />
        </div>
      )}
      <div className={styles.statusLine} data-tone={status}>
        {status === 'none' && 'No budget set.'}
        {status === 'ok' && `${formatHours(budget! - project.actual_hours)} left`}
        {status === 'warning' && `Nearly over budget: ${formatHours(budget! - project.actual_hours)} left`}
        {status === 'over' && `Over budget by ${formatHours(project.actual_hours - budget!)}`}
      </div>
      {editing && (
        <BudgetEditor
          initial={budget}
          onCancel={() => setEditing(false)}
          onSave={async (value) => {
            await onSave({ budgeted_hours: value })
            setEditing(false)
          }}
        />
      )}
    </Card>
  )
}

function BudgetEditor({
  initial,
  onSave,
  onCancel,
}: {
  initial: number | null
  onSave: (value: number | null) => Promise<void>
  onCancel: () => void
}) {
  const [value, setValue] = useState(initial == null ? '' : String(initial))
  const invalid = value !== '' && (Number.isNaN(Number(value)) || Number(value) < 0)
  const submit = () => {
    if (invalid) return
    void onSave(value === '' ? null : Number(value)).catch(() => {})
  }
  return (
    <form
      className={styles.inlineForm}
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
    >
      <label htmlFor="workspace-budget" className={styles.srOnly}>
        Budgeted hours
      </label>
      <input
        id="workspace-budget"
        className={styles.input}
        type="number"
        min={0}
        step="0.5"
        autoFocus
        placeholder="Hours"
        value={value}
        aria-invalid={invalid}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
      />
      <button type="submit" className={styles.smallButton} disabled={invalid}>
        Save
      </button>
      <button type="button" className={styles.linkButton} onClick={onCancel}>
        Cancel
      </button>
    </form>
  )
}

function DeadlineCard({ project, canEdit, onSave }: { project: ProjectDetail; canEdit: boolean; onSave: Save }) {
  const { status, daysLeft } = deadlineStatus(project.deadline)
  return (
    <Card
      icon={<CalendarClock size={16} />}
      tone="teal"
      title="Deadline"
      aside={
        status !== 'none' && (
          <span className={styles.pill} data-tone={status}>
            {DEADLINE_LABELS[status]}
          </span>
        )
      }
    >
      {project.deadline ? (
        <div className={styles.timeFigures}>
          <span className={styles.bigNumber} data-tone={status}>
            {countdownText(daysLeft!)}
          </span>
          <span className={styles.subtle}>{format(parseISO(project.deadline), 'EEE d MMM yyyy')}</span>
        </div>
      ) : (
        <div className={styles.statusLine}>No deadline set.</div>
      )}
      {canEdit && (
        <div className={styles.inlineForm}>
          <label htmlFor="workspace-deadline" className={styles.srOnly}>
            Deadline
          </label>
          <input
            id="workspace-deadline"
            className={styles.input}
            type="date"
            // Keyed so a deadline changed elsewhere refreshes the box.
            key={project.deadline ?? 'none'}
            defaultValue={project.deadline ?? ''}
            onChange={(e) => {
              if (e.target.value && e.target.value !== project.deadline) void onSave({ deadline: e.target.value }).catch(() => {})
            }}
          />
          {project.deadline && (
            <Tooltip label="Clear deadline" side="left">
              <button
                type="button"
                className={styles.iconButton}
                onClick={() => void onSave({ deadline: null }).catch(() => {})}
                aria-label="Clear deadline"
              >
                <X size={14} />
              </button>
            </Tooltip>
          )}
        </div>
      )}
    </Card>
  )
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

/** Saves a second after typing stops, and on leaving the box. */
const AUTOSAVE_DELAY_MS = 1000

function AutosaveText({
  id,
  label,
  value,
  canEdit,
  placeholder,
  emptyText,
  rows = 3,
  onSave,
}: {
  id: string
  label: string
  value: string
  canEdit: boolean
  placeholder: string
  emptyText: string
  rows?: number
  onSave: (value: string) => Promise<unknown>
}) {
  const [draft, setDraft] = useState(value)
  const [saved, setSaved] = useState(value)
  const [state, setState] = useState<SaveState>('idle')

  // Someone else changed it and there are no unsaved edits here: show their version.
  if (value !== saved && draft === saved) {
    setDraft(value)
    setSaved(value)
  }

  const flush = () => {
    const next = draft
    if (next === saved) return
    setState('saving')
    onSave(next).then(
      () => {
        setSaved(next)
        setState('saved')
      },
      () => setState('error'),
    )
  }

  useEffect(() => {
    if (draft === saved) return
    const timer = setTimeout(flush, AUTOSAVE_DELAY_MS)
    return () => clearTimeout(timer)
    // flush is recreated each render with the same draft/saved this effect depends on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, saved])

  if (!canEdit) {
    return value ? <p className={styles.readText}>{value}</p> : <p className={styles.subtle}>{emptyText}</p>
  }

  return (
    <>
      <label htmlFor={id} className={styles.srOnly}>
        {label}
      </label>
      <textarea
        id={id}
        className={styles.textarea}
        rows={rows}
        placeholder={placeholder}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value)
          setState('idle')
        }}
        onBlur={flush}
      />
      <div className={styles.saveState} aria-live="polite">
        {state === 'saving' && 'Saving…'}
        {state === 'saved' && draft === saved && 'Saved'}
        {state === 'error' && <span className={styles.errorText}>Couldn't save. Keep typing to retry.</span>}
      </div>
    </>
  )
}
