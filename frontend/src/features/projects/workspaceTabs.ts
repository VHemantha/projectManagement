import { Calendar, ClipboardList, LayoutDashboard, ListTodo, type LucideIcon, Settings, SquareKanban, TrendingDown } from 'lucide-react'

import type { ProjectDetail } from '@/api/types'
import { FEATURES } from '@/lib/features'

/** The sections of a project page, picked with ?tab=. Kanban comes first and is the default. */
export type WorkspaceTab = 'kanban' | 'summary' | 'backlog' | 'tasks' | 'timeline' | 'reports' | 'settings'

export const DEFAULT_TAB: WorkspaceTab = 'kanban'

export interface WorkspaceTabDef {
  id: WorkspaceTab
  label: string
  icon: LucideIcon
}

/** Scrum views (sprint board, Backlog, sprint reports) only for Scrum projects with the flag on;
 * with it off, Scrum projects behave like Kanban ones. */
export function isScrumWorkspace(project: Pick<ProjectDetail, 'project_type'>): boolean {
  return FEATURES.scrum && project.project_type === 'scrum'
}

export function workspaceTabs(project: Pick<ProjectDetail, 'project_type'>): WorkspaceTabDef[] {
  const scrum = isScrumWorkspace(project)
  return [
    { id: 'kanban', label: scrum ? 'Sprint board' : 'Kanban', icon: SquareKanban },
    ...(FEATURES.summary ? [{ id: 'summary' as const, label: 'Summary', icon: LayoutDashboard }] : []),
    ...(scrum ? [{ id: 'backlog' as const, label: 'Backlog', icon: ListTodo }] : []),
    { id: 'tasks', label: 'Tasks', icon: ClipboardList },
    { id: 'timeline', label: 'Timeline', icon: Calendar },
    ...(scrum ? [{ id: 'reports' as const, label: 'Reports', icon: TrendingDown }] : []),
    { id: 'settings', label: 'Settings', icon: Settings },
  ]
}

/** The tab to show for a ?tab= value: unknown or hidden tabs fall back to Kanban. The tasks tab
 * was "jobs" until Oct 2026, so ?tab=jobs still opens it. */
export function resolveTab(param: string | null, project: Pick<ProjectDetail, 'project_type'>): WorkspaceTab {
  const tabs = workspaceTabs(project)
  const wanted = param === 'jobs' ? 'tasks' : param
  return tabs.find((t) => t.id === wanted)?.id ?? DEFAULT_TAB
}

/** Old sub-page URLs (/projects/KEY/board …) and the tab they now open. */
const LEGACY_SECTIONS: Record<string, WorkspaceTab> = {
  board: 'kanban',
  summary: 'summary',
  backlog: 'backlog',
  issues: 'tasks',
  timeline: 'timeline',
  reports: 'reports',
  settings: 'settings',
}

export function tabForLegacySection(section: string | undefined): WorkspaceTab {
  return (section && LEGACY_SECTIONS[section]) || DEFAULT_TAB
}

export function workspaceUrl(key: string, tab?: WorkspaceTab): string {
  return tab ? `/projects/${key}?tab=${tab}` : `/projects/${key}`
}
