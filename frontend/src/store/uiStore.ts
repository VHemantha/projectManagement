import { create } from 'zustand'

/** What the Create task form opens with: whatever the page knows. Every field is optional; the
 * form derives the workspace and sub-workspace from the project when they are not given. */
export interface CreateIssueDefaults {
  projectKey?: string
  teamId?: number
  clientId?: number
  /** The board column it was created from: its status (same project) or category (a board across projects). */
  statusId?: number
  statusCategory?: 'todo' | 'in_progress' | 'done'
  columnName?: string
  epicId?: number
  assigneeId?: number
}

interface UiState {
  issueModalKey: string | null
  openIssueModal: (key: string) => void
  closeIssueModal: () => void

  createIssueOpen: boolean
  createIssueDefaultProjectKey: string | null
  createIssueDefaults: CreateIssueDefaults
  /** A project key (older callers) or the defaults the page knows. */
  openCreateIssue: (defaults?: string | CreateIssueDefaults | null) => void
  closeCreateIssue: () => void

  quickSearchOpen: boolean
  toggleQuickSearch: () => void
  closeQuickSearch: () => void
}

export const useUiStore = create<UiState>()((set) => ({
  issueModalKey: null,
  openIssueModal: (key) => set({ issueModalKey: key }),
  closeIssueModal: () => set({ issueModalKey: null }),

  createIssueOpen: false,
  createIssueDefaultProjectKey: null,
  createIssueDefaults: {},
  openCreateIssue: (defaults) => {
    const d: CreateIssueDefaults = typeof defaults === 'string' ? { projectKey: defaults } : (defaults ?? {})
    set({ createIssueOpen: true, createIssueDefaultProjectKey: d.projectKey ?? null, createIssueDefaults: d })
  },
  closeCreateIssue: () => set({ createIssueOpen: false }),

  quickSearchOpen: false,
  toggleQuickSearch: () => set((s) => ({ quickSearchOpen: !s.quickSearchOpen })),
  closeQuickSearch: () => set({ quickSearchOpen: false }),
}))
