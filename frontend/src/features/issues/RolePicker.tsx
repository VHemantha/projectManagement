import { useId } from 'react'

import styles from './IssueView.module.css'
import type { User } from '@/api/types'
import { Avatar } from '@/design-system'

interface RolePickerProps {
  label: string
  value: User | null
  users: User[] | undefined
  onChange: (userId: number | null) => void
  emptyLabel?: string
  /** A longer explanation of the role, shown on hover. */
  hint?: string
}

/** One person on the task (Team lead, Accountant, Reviewer, Responsible): their avatar beside a
 * picker of people, as in the task view's design. */
export function RolePicker({ label, value, users, onChange, emptyLabel = 'Unassigned', hint }: RolePickerProps) {
  const id = useId()
  return (
    <div className={styles.panelRow}>
      <label className={styles.panelLabel} htmlFor={id} title={hint}>
        {label}
      </label>
      <div className={styles.assigneeRow}>
        {value ? (
          <Avatar name={value.display_name} src={value.avatar} size={32} userId={value.id} interactive />
        ) : (
          // Nobody in the role: a grey placeholder, as in the design.
          <span className={styles.emptyAvatar} aria-hidden="true">
            {emptyLabel.slice(0, 2).toUpperCase()}
          </span>
        )}
        <select
          id={id}
          className={styles.panelSelect}
          value={value?.id ?? ''}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">{emptyLabel}</option>
          {users?.map((u) => (
            <option key={u.id} value={u.id}>
              {u.display_name}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
