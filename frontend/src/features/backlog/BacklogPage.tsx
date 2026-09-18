import {
  DndContext,
  type DragEndEvent,
  type DragOverEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Plus } from 'lucide-react'
import { useEffect, useState } from 'react'

import styles from './BacklogPage.module.css'
import { CompleteSprintDialog } from './CompleteSprintDialog'
import { IssueRow } from './IssueRow'
import { StartSprintDialog } from './StartSprintDialog'
import { useCreateIssue, useIssueTypes, useIssues, useMoveIssue } from '@/api/issues'
import { useCreateSprint, useSprints } from '@/api/sprints'
import type { IssueListItem, Sprint } from '@/api/types'
import { Button } from '@/design-system'
import { useProjectContext } from '@/features/projects/useProjectContext'

type SectionId = 'backlog' | number

function sectionKey(id: SectionId) {
  return String(id)
}

function QuickAdd({ projectKey, sprintId, defaultTypeId }: { projectKey: string; sprintId: number | null; defaultTypeId: number | undefined }) {
  const createIssue = useCreateIssue()
  const [value, setValue] = useState('')
  const [active, setActive] = useState(false)

  const submit = () => {
    if (!value.trim() || !defaultTypeId) return
    createIssue.mutate(
      { project: projectKey, summary: value.trim(), issue_type_id: defaultTypeId, sprint_id: sprintId },
      { onSuccess: () => setValue('') },
    )
  }

  if (!active) {
    return (
      <div className={styles.quickAdd}>
        <Button variant="subtle" size="sm" onClick={() => setActive(true)}>
          <Plus size={14} /> Create issue
        </Button>
      </div>
    )
  }

  return (
    <div className={styles.quickAdd}>
      <input
        className={styles.quickAddInput}
        autoFocus
        placeholder="What needs to be done?"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') submit()
          if (e.key === 'Escape') setActive(false)
        }}
        onBlur={() => {
          if (!value.trim()) setActive(false)
        }}
      />
    </div>
  )
}

function DroppableSection({ id, children }: { id: SectionId; children: React.ReactNode }) {
  const { setNodeRef } = useDroppable({ id: sectionKey(id) })
  return (
    <div ref={setNodeRef} className={styles.sectionBody}>
      {children}
    </div>
  )
}

export function BacklogPage() {
  const { project } = useProjectContext()
  const { data: sprints } = useSprints(project.key)
  const { data: issuesPage } = useIssues(
    { project: project.key, no_parent: true, exclude_type: 'Epic', page_size: 300, ordering: 'rank' },
    true,
  )
  const { data: epicsPage } = useIssues({ project: project.key, issue_type: 'Epic', page_size: 100 })
  const { data: storyTypes } = useIssueTypes(project.key, false)
  const createSprint = useCreateSprint(project.key)
  const moveIssue = useMoveIssue()

  const [selectedEpicIds, setSelectedEpicIds] = useState<Set<number>>(new Set())
  const [sections, setSections] = useState<Record<string, number[]>>({})
  const [issuesById, setIssuesById] = useState<Record<number, IssueListItem>>({})
  const [activeId, setActiveId] = useState<number | null>(null)
  const [startingSprint, setStartingSprint] = useState<Sprint | null>(null)
  const [completingSprint, setCompletingSprint] = useState<Sprint | null>(null)
  const [dragging, setDragging] = useState(false)

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  useEffect(() => {
    if (dragging || !issuesPage) return
    const byId: Record<number, IssueListItem> = {}
    const grouped: Record<string, number[]> = { backlog: [] }
    for (const sprint of sprints ?? []) grouped[sectionKey(sprint.id)] = []
    for (const issue of issuesPage.results) {
      byId[issue.id] = issue
      const key = issue.sprint ? sectionKey(issue.sprint.id) : 'backlog'
      if (!grouped[key]) grouped[key] = []
      grouped[key].push(issue.id)
    }
    setIssuesById(byId)
    setSections(grouped)
  }, [issuesPage, sprints, dragging])

  const storyTypeId = storyTypes?.find((t) => t.name === 'Story')?.id ?? storyTypes?.[0]?.id

  const visibleIssues = (ids: number[]) =>
    ids
      .map((id) => issuesById[id])
      .filter((issue): issue is IssueListItem => !!issue)
      .filter((issue) => selectedEpicIds.size === 0 || (issue.epic && selectedEpicIds.has(issue.epic.id)))

  function findContainer(id: number | string): string | undefined {
    if (typeof id === 'string' && sections[id]) return id
    return Object.keys(sections).find((key) => sections[key].includes(id as number))
  }

  const handleDragStart = (event: DragStartEvent) => {
    setDragging(true)
    setActiveId(event.active.id as number)
  }

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event
    if (!over) return
    const activeContainer = findContainer(active.id as number)
    const overContainer = findContainer(over.id as number | string)
    if (!activeContainer || !overContainer || activeContainer === overContainer) return

    setSections((prev) => {
      const activeItems = prev[activeContainer].filter((id) => id !== active.id)
      const overItems = [...prev[overContainer]]
      const overIndex = overItems.indexOf(over.id as number)
      const insertAt = overIndex >= 0 ? overIndex : overItems.length
      overItems.splice(insertAt, 0, active.id as number)
      return { ...prev, [activeContainer]: activeItems, [overContainer]: overItems }
    })
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setDragging(false)
    setActiveId(null)
    if (!over) return

    const container = findContainer(active.id as number)
    if (!container) return

    setSections((prev) => {
      const items = [...prev[container]]
      const oldIndex = items.indexOf(active.id as number)
      const overIndex = items.indexOf(over.id as number)
      let newIndex = overIndex >= 0 ? overIndex : items.length - 1
      if (oldIndex === -1) return prev
      items.splice(oldIndex, 1)
      items.splice(newIndex, 0, active.id as number)

      const finalIndex = items.indexOf(active.id as number)
      const beforeId = finalIndex > 0 ? items[finalIndex - 1] : null
      const afterId = finalIndex < items.length - 1 ? items[finalIndex + 1] : null
      const issue = issuesById[active.id as number]
      const targetSprintId = container === 'backlog' ? null : Number(container)

      if (issue) {
        moveIssue.mutate({
          key: issue.key,
          before_id: beforeId,
          after_id: afterId,
          sprint_id: issue.sprint?.id !== targetSprintId ? targetSprintId : undefined,
        })
      }
      return { ...prev, [container]: items }
    })
  }

  const openSprints = (sprints ?? []).filter((s) => s.state !== 'closed')
  const activeIssue = activeId ? issuesById[activeId] : null

  return (
    <div className={styles.layout}>
      <aside className={styles.epicPanel}>
        <div className={styles.epicPanelTitle}>Epics</div>
        {(epicsPage?.results ?? []).map((epic) => (
          <div
            key={epic.id}
            className={`${styles.epicChip} ${selectedEpicIds.has(epic.id) ? styles.active : ''}`}
            onClick={() =>
              setSelectedEpicIds((prev) => {
                const next = new Set(prev)
                if (next.has(epic.id)) next.delete(epic.id)
                else next.add(epic.id)
                return next
              })
            }
          >
            <span className={styles.epicDot} style={{ background: epic.epic?.epic_color ?? '#8777D9' }} />
            {epic.summary}
          </div>
        ))}
        {(epicsPage?.results.length ?? 0) === 0 && (
          <div style={{ fontSize: 12, color: 'var(--tf-text-subtle)' }}>No epics yet.</div>
        )}
      </aside>

      <div className={styles.main}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <h1 className={styles.pageTitle} style={{ marginBottom: 0 }}>
            Backlog
          </h1>
          <Button
            variant="secondary"
            size="sm"
            style={{ marginLeft: 'auto' }}
            onClick={() => createSprint.mutate({ name: `Sprint ${(sprints?.length ?? 0) + 1}` })}
          >
            <Plus size={14} /> Sprint
          </Button>
        </div>

        <DndContext
          sensors={sensors}
          collisionDetection={closestCorners}
          onDragStart={handleDragStart}
          onDragOver={handleDragOver}
          onDragEnd={handleDragEnd}
        >
          {(sprints ?? [])
            .filter((s) => s.state !== 'closed')
            .map((sprint) => {
              const ids = sections[sectionKey(sprint.id)] ?? []
              const issues = visibleIssues(ids)
              return (
                <div className={styles.section} key={sprint.id}>
                  <div className={styles.sectionHeader}>
                    <span className={styles.sectionTitle}>{sprint.name}</span>
                    {sprint.state === 'active' && <span className={styles.stateBadge}>Active</span>}
                    {sprint.start_date && sprint.end_date && (
                      <span className={styles.sectionMeta}>
                        {sprint.start_date} – {sprint.end_date}
                      </span>
                    )}
                    <span className={styles.sectionMeta}>{issues.length} issues</span>
                    <div className={styles.sectionActions}>
                      {sprint.state === 'future' && (
                        <Button variant="secondary" size="sm" onClick={() => setStartingSprint(sprint)}>
                          Start sprint
                        </Button>
                      )}
                      {sprint.state === 'active' && (
                        <Button variant="secondary" size="sm" onClick={() => setCompletingSprint(sprint)}>
                          Complete sprint
                        </Button>
                      )}
                    </div>
                  </div>
                  <SortableContext items={ids} strategy={verticalListSortingStrategy}>
                    <DroppableSection id={sprint.id}>
                      {issues.length === 0 ? (
                        <div className={styles.emptyDrop}>Drag issues here, or create one below.</div>
                      ) : (
                        issues.map((issue) => <IssueRow key={issue.id} issue={issue} />)
                      )}
                    </DroppableSection>
                  </SortableContext>
                  <QuickAdd projectKey={project.key} sprintId={sprint.id} defaultTypeId={storyTypeId} />
                </div>
              )
            })}

          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionTitle}>Backlog</span>
              <span className={styles.sectionMeta}>{visibleIssues(sections.backlog ?? []).length} issues</span>
            </div>
            <SortableContext items={sections.backlog ?? []} strategy={verticalListSortingStrategy}>
              <DroppableSection id="backlog">
                {visibleIssues(sections.backlog ?? []).length === 0 ? (
                  <div className={styles.emptyDrop}>Backlog is empty.</div>
                ) : (
                  visibleIssues(sections.backlog ?? []).map((issue) => <IssueRow key={issue.id} issue={issue} />)
                )}
              </DroppableSection>
            </SortableContext>
            <QuickAdd projectKey={project.key} sprintId={null} defaultTypeId={storyTypeId} />
          </div>

          <DragOverlay>{activeIssue ? <IssueRow issue={activeIssue} /> : null}</DragOverlay>
        </DndContext>
      </div>

      <StartSprintDialog sprint={startingSprint} onClose={() => setStartingSprint(null)} />
      <CompleteSprintDialog
        sprint={completingSprint}
        otherOpenSprints={openSprints.filter((s) => s.id !== completingSprint?.id && s.state === 'future')}
        onClose={() => setCompletingSprint(null)}
      />
    </div>
  )
}
