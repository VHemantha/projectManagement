import styles from './PlaceholderPage.module.css'

export function PlaceholderPage({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.title}>{title}</div>
      {hint && <div>{hint}</div>}
    </div>
  )
}
