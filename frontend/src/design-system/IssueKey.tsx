import styles from './Badge.module.css'

export function IssueKey({ value }: { value: string }) {
  return <span className={styles.key}>{value}</span>
}
