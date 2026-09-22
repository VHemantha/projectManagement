import styles from './IssueView.module.css'
import type { User } from '@/api/types'
import { Avatar } from '@/design-system'

interface RolePickerProps {
  label: string
  value: User | null
  users: User[] | undefined
  onChange: (userId: number | null) => void
  emptyLabel?: string
}

/** Shared "avatar + <select> bound to a set of users" control — the same interaction the
 * Assignee field always used, now reused for Preparer/Reviewer/Current Responsible too
 * instead of three more copies of the same inline markup. */
export function RolePicker({ label, value, users, onChange, emptyLabel = 'Unassigned' }: RolePickerProps) {
  return (
    <div className={styles.panelRow}>
      <span className={styles.panelLabel}>{label}</span>
      <div className={styles.assigneeRow}>
        <Avatar name={value?.display_name ?? emptyLabel} src={value?.avatar} size={24} userId={value?.id} interactive />
        <select
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
