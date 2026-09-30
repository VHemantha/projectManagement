/** Sentence case for app-generated labels: "in_progress" -> "In progress", "admin" -> "Admin".
 * Only the first letter changes, so names and acronyms inside the text are left alone. */
export function sentenceCase(text: string): string {
  const t = text.replace(/_/g, ' ').trim()
  return t ? t[0].toUpperCase() + t.slice(1) : t
}

/** Display names for workflow status categories. */
export const CATEGORY_LABELS: Record<'todo' | 'in_progress' | 'done', string> = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
}
