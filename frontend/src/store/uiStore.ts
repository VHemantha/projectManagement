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
  /** The task windows open, the one showing last (AFIT, 5 Nov 2026): opening a sub-task or a linked
   * task from a task goes on top, and closing it goes back to the task underneath. */
  issueModalStack: string[]
  openIssueModal: (key: string) => void
  /** Close the window showing; the one underneath (if any) shows again. */
  closeIssueModal: () => void
  closeAllIssueModals: () => void

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
  issueModalStack: [],
  openIssueModal: (key) =>
    set((s) => {
      if (s.issueModalKey === key) return {}
      const stack = s.issueModalKey ? [...s.issueModalStack.filter((k) => k !== key), key] : [key]
      return { issueModalKey: key, issueModalStack: stack }
    }),
  closeIssueModal: () =>
    set((s) => {
      const stack = s.issueModalStack.slice(0, -1)
      return { issueModalKey: stack[stack.length - 1] ?? null, issueModalStack: stack }
    }),
  closeAllIssueModals: () => set({ issueModalKey: null, issueModalStack: [] }),

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
