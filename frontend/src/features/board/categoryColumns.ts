import type { BoardColumn } from '@/api/types'

/** Generic 3-column layout for boards that aggregate issues across projects
 * with different workflows (Team board, My Work), where no single project's
 * concrete status ids apply to every issue. */
export const CATEGORY_COLUMNS: BoardColumn[] = [
  { name: 'To Do', status_ids: [], wip_limit: null, category: 'todo' },
  { name: 'In Progress', status_ids: [], wip_limit: null, category: 'in_progress' },
  { name: 'Done', status_ids: [], wip_limit: null, category: 'done' },
]
