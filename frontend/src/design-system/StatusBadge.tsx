import styles from './Badge.module.css'

export type StatusCategory = 'todo' | 'in_progress' | 'done'

const CATEGORY_STYLE: Record<StatusCategory, { bg: string; text: string }> = {
  todo: { bg: 'var(--tf-status-todo-bg)', text: 'var(--tf-status-todo-text)' },
  in_progress: { bg: 'var(--tf-status-inprogress-bg)', text: 'var(--tf-status-inprogress-text)' },
  done: { bg: 'var(--tf-status-done-bg)', text: 'var(--tf-status-done-text)' },
}

interface StatusBadgeProps {
  label: string
  category: StatusCategory
}

export function StatusBadge({ label, category }: StatusBadgeProps) {
  const c = CATEGORY_STYLE[category]
  return (
    <span className={styles.badge} style={{ background: c.bg, color: c.text }}>
      {label}
    </span>
  )
}
