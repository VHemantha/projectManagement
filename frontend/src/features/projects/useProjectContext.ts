import { createContext, useContext } from 'react'

import type { ProjectDetail } from '@/api/types'

/** The workspace whose page is open, provided by ProjectLayout to every tab. */
export const WorkspaceContext = createContext<{ project: ProjectDetail } | null>(null)

export function useProjectContext() {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('useProjectContext must be used inside a project page')
  return value
}
