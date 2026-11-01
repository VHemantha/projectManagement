import {
  DndContext,
  type DragEndEvent,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { format, parseISO, subDays } from 'date-fns'
import { Check, ChevronRight, Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import styles from './DashboardHomePage.module.css'
import {
  type DailyGoal,
  useCarryOverGoal,
  useCreateDailyGoal,
  useDailyGoalsRange,
  useUpdateDailyGoal,
} from '@/api/dailyGoals'
import { useIssues } from '@/api/issues'
import { completionLabel } from '@/lib/plans'
import { IssueKey } from '@/design-system'
import { useUiStore } from '@/store/uiStore'

const STRIP_DAYS = 7

function dayColor(goals: DailyGoal[]): string {
  if (goals.length === 0) return 'var(--tf-border)'
  const achieved = goals.filter((g) => g.status === 'achieved').length
  const notAchieved = goals.filter((g) => g.status === 'not_achieved').length
  if (notAchieved > 0 && achieved > 0) return 'var(--tf-warning)'
  if (notAchieved > 0) return 'var(--tf-danger)'
  if (achieved === goals.length) return 'var(--tf-success)'
  return 'var(--tf-border)'
}

/** One line under a plan item: the hours for the day, the completion date, and what the task's
 * record and the team lead say. */
export function PlanMeta({ goal }: { goal: DailyGoal }) {
  const parts: string[] = []
  if (goal.planned_hours != null) parts.push(`${Number(goal.planned_hours.toFixed(2))} hr${goal.planned_hours === 1 ? '' : 's'} today`)
  if (goal.complete_by) parts.push(completionLabel(goal.complete_by, goal.date))
  const overdue = goal.complete_by && !goal.task_done && goal.linked_issue && goal.complete_by < format(new Date(), 'yyyy-MM-dd')
  if (!parts.length && !goal.task_done && !goal.lead_check) return null
  return (
    <div style={{ fontSize: 11, color: 'var(--tf-text-subtle)', marginTop: 2, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {parts.length > 0 && <span>{parts.join(' · ')}</span>}
      {goal.task_done && <span style={{ color: 'var(--tf-success)' }}>Task finished {format(parseISO(goal.task_done), 'd MMM')}</span>}
      {overdue && <span style={{ color: 'var(--tf-danger)' }}>Completion date passed</span>}
      {goal.lead_check === 'confirmed' && <span style={{ color: 'var(--tf-success)' }}>Checked by {goal.checked_by?.display_name ?? 'team lead'}</span>}
      {goal.lead_check === 'not_done' && <span style={{ color: 'var(--tf-danger)' }}>Team lead: not done</span>}
    </div>
  )
}

/** Add an item to the day's plan: what (or a task), the hours for today, and the completion date. */
function PlanItemForm({ date }: { date: string }) {
  const createGoal = useCreateDailyGoal()
  const [text, setText] = useState('')
  const [hours, setHours] = useState('')
  const [completeBy, setCompleteBy] = useState(date)
  const [taskSearch, setTaskSearch] = useState('')
  const [task, setTask] = useState<{ id: number; key: string; summary: string } | null>(null)
  const { data: found } = useIssues({ search: taskSearch, no_parent: true, page_size: 6 }, taskSearch.trim().length >= 2)

  const add = () => {
    if (!text.trim() && !task) return
    createGoal.mutate(
      {
        date,
        text: text.trim(),
        linked_issue_id: task?.id ?? null,
        planned_hours: hours ? Number(hours) : null,
        complete_by: completeBy || null,
      },
      {
        onSuccess: () => {
          setText('')
          setHours('')
          setTask(null)
          setTaskSearch('')
          setCompleteBy(date)
        },
      },
    )
  }
  const field = { fontSize: 13, height: 30, border: '1px solid var(--tf-border)', borderRadius: 4, padding: '0 8px' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }} aria-label="Add to the plan" role="group">
      <input
        aria-label="What will you do?"
        placeholder={task ? 'Leave blank to use the task' : 'What will you do? e.g. ABC Ltd Preparation'}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && add()}
        style={field}
      />
      {task ? (
        <div style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
          <IssueKey value={task.key} /> {task.summary}
          <button type="button" onClick={() => setTask(null)} style={{ fontSize: 11, marginLeft: 'auto' }}>
            Remove task
          </button>
        </div>
      ) : (
        <div style={{ position: 'relative' }}>
          <input
            aria-label="Task (optional)"
            placeholder="Link a task (optional): search by key or name"
            value={taskSearch}
            onChange={(e) => setTaskSearch(e.target.value)}
            style={{ ...field, width: '100%', boxSizing: 'border-box' }}
          />
          {taskSearch.trim().length >= 2 && (found?.results.length ?? 0) > 0 && (
            <div role="listbox" style={{ border: '1px solid var(--tf-border)', borderRadius: 4, marginTop: 2, background: 'var(--tf-surface)' }}>
              {found!.results.map((r) => (
                <div
                  key={r.id}
                  role="option"
                  aria-selected={false}
                  style={{ padding: '4px 8px', cursor: 'pointer', fontSize: 12 }}
                  onClick={() => {
                    setTask({ id: r.id, key: r.key, summary: r.summary })
                    setTaskSearch('')
                  }}
                >
                  {r.key} — {r.summary}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
          Hours today
          <input
            type="number"
            min="0.25"
            max="24"
            step="0.25"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            style={{ ...field, width: 70 }}
          />
        </label>
        <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
          Completion
          <input type="date" min={date} value={completeBy} onChange={(e) => setCompleteBy(e.target.value)} style={field} />
        </label>
        <button
          type="button"
          onClick={add}
          aria-label="Add to plan"
          disabled={createGoal.isPending || (!text.trim() && !task)}
          style={{ border: '1px solid var(--tf-border)', borderRadius: 4, background: 'var(--tf-surface)', cursor: 'pointer', padding: '0 8px', height: 30, marginLeft: 'auto' }}
        >
          <Plus size={14} />
        </button>
      </div>
    </div>
  )
}

function GoalRow({ goal }: { goal: DailyGoal }) {
  const update = useUpdateDailyGoal()
  const carryOver = useCarryOverGoal()
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState('')
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: goal.id })

  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }

  const submitNotAchieved = () => {
    if (!note.trim()) return
    update.mutate({ id: goal.id, status: 'not_achieved', note: note.trim() })
    setNoteOpen(false)
  }

  return (
    <div ref={setNodeRef} style={style} className={styles.goalRow}>
      <span {...attributes} {...listeners} className={styles.goalDragHandle}>
        ⠿
      </span>
      <button
        type="button"
        className={styles.goalCheck}
        data-status={goal.status}
        onClick={() => update.mutate({ id: goal.id, status: goal.status === 'achieved' ? 'planned' : 'achieved' })}
        aria-label="Toggle achieved"
      >
        {goal.status === 'achieved' && <Check size={12} />}
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13,
            textDecoration: goal.status === 'achieved' ? 'line-through' : undefined,
            color: goal.status === 'achieved' ? 'var(--tf-text-subtle)' : 'var(--tf-text)',
          }}
        >
          {goal.text}
          {goal.linked_issue && (
            <span style={{ marginLeft: 6, cursor: 'pointer' }} onClick={() => openIssueModal(goal.linked_issue!.key)}>
              <IssueKey value={goal.linked_issue.key} />
            </span>
          )}
        </div>
        <PlanMeta goal={goal} />
        {goal.status === 'not_achieved' && goal.note && (
          <div style={{ fontSize: 11, color: 'var(--tf-danger)', marginTop: 2 }}>{goal.note}</div>
        )}
        {noteOpen && (
          <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
            <input
              autoFocus
              placeholder="Why not? (required)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitNotAchieved()}
              style={{ flex: 1, fontSize: 12, height: 26, border: '1px solid var(--tf-border)', borderRadius: 4, padding: '0 6px' }}
            />
            <button type="button" onClick={submitNotAchieved} style={{ fontSize: 11 }}>
              Save
            </button>
          </div>
        )}
      </div>
      {goal.status !== 'achieved' && goal.status !== 'not_achieved' && (
        <button
          type="button"
          title="Mark not achieved"
          onClick={() => setNoteOpen((v) => !v)}
          style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--tf-text-subtle)' }}
        >
          <X size={13} />
        </button>
      )}
      {goal.status === 'not_achieved' && (
        <button
          type="button"
          title="Carry over to tomorrow"
          onClick={() => carryOver.mutate(goal.id)}
          style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--tf-primary)' }}
        >
          <ChevronRight size={13} />
        </button>
      )}
    </div>
  )
}

export function DailyGoalsWidget() {
  const today = format(new Date(), 'yyyy-MM-dd')
  const rangeStart = format(subDays(new Date(), STRIP_DAYS - 1), 'yyyy-MM-dd')
  const [viewDate, setViewDate] = useState(today)

  const { data: rangeGoals } = useDailyGoalsRange(rangeStart, today)
  const updateGoal = useUpdateDailyGoal()
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  const byDate = useMemo(() => {
    const map = new Map<string, DailyGoal[]>()
    for (const g of rangeGoals ?? []) {
      const list = map.get(g.date) ?? []
      list.push(g)
      map.set(g.date, list)
    }
    for (const list of map.values()) list.sort((a, b) => a.order - b.order)
    return map
  }, [rangeGoals])

  const viewGoals = byDate.get(viewDate) ?? []
  const strip = Array.from({ length: STRIP_DAYS }, (_, i) => format(subDays(new Date(), STRIP_DAYS - 1 - i), 'yyyy-MM-dd'))

  const yesterday = format(subDays(new Date(), 1), 'yyyy-MM-dd')
  const unmarkedYesterday = (byDate.get(yesterday) ?? []).filter(
    (g) => g.status === 'planned' || g.status === 'in_progress',
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const ids = viewGoals.map((g) => g.id)
    const oldIndex = ids.indexOf(Number(active.id))
    const newIndex = ids.indexOf(Number(over.id))
    if (oldIndex === -1 || newIndex === -1) return
    const reordered = [...viewGoals]
    const [moved] = reordered.splice(oldIndex, 1)
    reordered.splice(newIndex, 0, moved)
    reordered.forEach((g, i) => {
      if (g.order !== i) updateGoal.mutate({ id: g.id, order: i })
    })
  }

  return (
    <div className={styles.card}>
      <div className={styles.cardTitle}>
        Morning plan {viewDate !== today && <span style={{ fontWeight: 400, color: 'var(--tf-text-subtle)' }}>— {viewDate}</span>}
      </div>

      {unmarkedYesterday.length > 0 && viewDate === today && (
        <div
          style={{
            fontSize: 12,
            background: 'var(--tf-warning-bg)',
            color: 'var(--tf-warning)',
            borderRadius: 6,
            padding: '6px 10px',
            marginBottom: 10,
            cursor: 'pointer',
          }}
          onClick={() => setViewDate(yesterday)}
        >
          You had {unmarkedYesterday.length} unmarked goal{unmarkedYesterday.length > 1 ? 's' : ''} from {yesterday} —
          update them?
        </div>
      )}

      {viewGoals.length === 0 ? (
        <div className={styles.empty}>Nothing planned for this day yet.</div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={viewGoals.map((g) => g.id)} strategy={verticalListSortingStrategy}>
            {viewGoals.map((goal) => (
              <GoalRow key={goal.id} goal={goal} />
            ))}
          </SortableContext>
        </DndContext>
      )}

      {viewDate === today && (
        <>
          {viewGoals.some((g) => g.planned_hours) && (
            <div style={{ fontSize: 12, color: 'var(--tf-text-subtle)', marginTop: 6 }}>
              {Number(viewGoals.reduce((s, g) => s + (g.planned_hours ?? 0), 0).toFixed(2))} hrs planned today
            </div>
          )}
          <PlanItemForm date={today} />
        </>
      )}

      <div style={{ display: 'flex', gap: 4, marginTop: 12 }}>
        {strip.map((d) => (
          <span
            key={d}
            title={d}
            onClick={() => setViewDate(d)}
            style={{
              width: 14,
              height: 14,
              borderRadius: '50%',
              background: dayColor(byDate.get(d) ?? []),
              cursor: 'pointer',
              border: d === viewDate ? '2px solid var(--tf-primary)' : '2px solid transparent',
            }}
          />
        ))}
      </div>
    </div>
  )
}
