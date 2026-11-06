import { beforeEach, describe, expect, it } from 'vitest'

import { useUiStore } from './uiStore'

const state = () => useUiStore.getState()

describe('task windows (AFIT, 5 Nov 2026)', () => {
  beforeEach(() => state().closeAllIssueModals())

  it('closing a sub-task goes back to its main task instead of closing both', () => {
    state().openIssueModal('ABC-12')
    state().openIssueModal('ABC-13') // a sub-task, opened from ABC-12
    expect(state().issueModalKey).toBe('ABC-13')
    state().closeIssueModal()
    expect(state().issueModalKey).toBe('ABC-12')
    state().closeIssueModal()
    expect(state().issueModalKey).toBeNull()
  })

  it('opening a task already underneath brings it back without repeating it', () => {
    state().openIssueModal('ABC-12')
    state().openIssueModal('ABC-13')
    state().openIssueModal('ABC-12')
    expect(state().issueModalStack).toEqual(['ABC-13', 'ABC-12'])
    state().openIssueModal('ABC-12')
    expect(state().issueModalStack).toEqual(['ABC-13', 'ABC-12'])
  })

  it('closing all leaves no window open', () => {
    state().openIssueModal('ABC-12')
    state().openIssueModal('ABC-13')
    state().closeAllIssueModals()
    expect(state().issueModalKey).toBeNull()
    expect(state().issueModalStack).toEqual([])
  })
})
