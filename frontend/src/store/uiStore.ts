import { create } from 'zustand'

interface UiState {
  issueModalKey: string | null
  openIssueModal: (key: string) => void
  closeIssueModal: () => void

  createIssueOpen: boolean
  createIssueDefaultProjectKey: string | null
  openCreateIssue: (defaultProjectKey?: string | null) => void
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
  openCreateIssue: (defaultProjectKey) =>
    set({ createIssueOpen: true, createIssueDefaultProjectKey: defaultProjectKey ?? null }),
  closeCreateIssue: () => set({ createIssueOpen: false }),

  quickSearchOpen: false,
  toggleQuickSearch: () => set((s) => ({ quickSearchOpen: !s.quickSearchOpen })),
  closeQuickSearch: () => set({ quickSearchOpen: false }),
}))
