import { useMemo, useState } from 'react'

import styles from './IssueFilterPanel.module.css'
import { useCreateFilter } from '@/api/search'
import type { IssueListItem, Priority } from '@/api/types'
import { Button } from '@/design-system'

export interface IssueFilters {
  types: Set<string>
  priorities: Set<Priority>
  assignees: Set<number>
}

export const EMPTY_FILTERS: IssueFilters = { types: new Set(), priorities: new Set(), assignees: new Set() }

export function applyIssueFilters(issues: IssueListItem[], filters: IssueFilters) {
  return issues.filter((issue) => {
    if (filters.types.size > 0 && !filters.types.has(issue.issue_type.name)) return false
    if (filters.priorities.size > 0 && !filters.priorities.has(issue.priority)) return false
    if (filters.assignees.size > 0 && !(issue.assignee && filters.assignees.has(issue.assignee.id))) return false
    return true
  })
}

function toggle<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

interface IssueFilterPanelProps {
  issues: IssueListItem[]
  filters: IssueFilters
  onChange: (filters: IssueFilters) => void
}

export function IssueFilterPanel({ issues, filters, onChange }: IssueFilterPanelProps) {
  const types = useMemo(() => [...new Set(issues.map((i) => i.issue_type.name))].sort(), [issues])
  const priorities: Priority[] = ['highest', 'high', 'medium', 'low', 'lowest']
  const assignees = useMemo(() => {
    const map = new Map<number, string>()
    for (const i of issues) if (i.assignee) map.set(i.assignee.id, i.assignee.display_name)
    return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [issues])

  const hasActiveFilters = filters.types.size + filters.priorities.size + filters.assignees.size > 0

  return (
    <div className={styles.panel}>
      {hasActiveFilters && (
        <button className={styles.clearBtn} onClick={() => onChange(EMPTY_FILTERS)}>
          Clear filters
        </button>
      )}

      <div className={styles.group}>
        <div className={styles.groupTitle}>Type</div>
        {types.map((t) => (
          <label key={t} className={styles.option}>
            <input
              type="checkbox"
              checked={filters.types.has(t)}
              onChange={() => onChange({ ...filters, types: toggle(filters.types, t) })}
            />
            {t}
          </label>
        ))}
      </div>

      <div className={styles.group}>
        <div className={styles.groupTitle}>Priority</div>
        {priorities.map((p) => (
          <label key={p} className={styles.option}>
            <input
              type="checkbox"
              checked={filters.priorities.has(p)}
              onChange={() => onChange({ ...filters, priorities: toggle(filters.priorities, p) })}
            />
            {p[0].toUpperCase() + p.slice(1)}
          </label>
        ))}
      </div>

      {assignees.length > 0 && (
        <div className={styles.group}>
          <div className={styles.groupTitle}>Assignee</div>
          {assignees.map(([id, name]) => (
            <label key={id} className={styles.option}>
              <input
                type="checkbox"
                checked={filters.assignees.has(id)}
                onChange={() => onChange({ ...filters, assignees: toggle(filters.assignees, id) })}
              />
              {name}
            </label>
          ))}
        </div>
      )}

      {hasActiveFilters && <SaveFilterForm filters={filters} />}
    </div>
  )
}

function SaveFilterForm({ filters }: { filters: IssueFilters }) {
  const createFilter = useCreateFilter()
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  if (createFilter.isSuccess && !saving) {
    return <div className={styles.groupTitle} style={{ color: 'var(--tf-success)' }}>Filter saved</div>
  }

  if (!saving) {
    return (
      <button className={styles.clearBtn} onClick={() => setSaving(true)}>
        Save as filter…
      </button>
    )
  }

  return (
    <div className={styles.group}>
      <input
        className={styles.option}
        style={{ border: '1px solid var(--tf-border)', borderRadius: 4, padding: '4px 8px', width: '100%' }}
        placeholder="Filter name"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Button
        variant="secondary"
        size="sm"
        style={{ marginTop: 6 }}
        disabled={!name.trim() || createFilter.isPending}
        onClick={() =>
          createFilter.mutate({
            name: name.trim(),
            query: {
              types: [...filters.types],
              priorities: [...filters.priorities],
              assignees: [...filters.assignees],
            },
          })
        }
      >
        Save
      </Button>
    </div>
  )
}
