import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { AiRulesPage } from './AiRulesPage'
import type { RuleLibrary } from '@/api/precheck'

const mocks = vi.hoisted(() => ({
  library: null as unknown as RuleLibrary,
  add: vi.fn((_payload: unknown, options?: { onSuccess?: () => void }) => options?.onSuccess?.()),
  setStatus: vi.fn(),
  filters: [] as unknown[],
}))

vi.mock('@/api/precheck', () => ({
  useRuleLibrary: (filters: unknown) => {
    mocks.filters.push(filters)
    return { data: mocks.library, isLoading: false, isError: false }
  },
  useAddRule: () => ({ mutate: mocks.add, isPending: false, isError: false }),
  useSetRuleStatus: () => ({ mutate: mocks.setStatus, isPending: false }),
}))

const LIBRARY = (canApprove: boolean): RuleLibrary => ({
  can_approve: canApprove,
  precheck_types: [],
  entity_types: [],
  lessons: [
    { id: 7, scope: 'firm', scope_label: 'All clients of this business nature', status: 'active', kind: 'missed', source: 'library',
      precheck_type: 'residential_rental', precheck_type_label: 'Residential rental', entity_type: '', entity_label: 'Any entity',
      rule: { title: 'Landlord insurance', when: 'The client owns a rental property.', do: 'Ask for the landlord insurance schedule.', why: 'The premium is deductible.' },
      drafting: 'drafted', item: 'Landlord insurance', note: 'Ask for the insurance schedule.', created_by: 'Ada', created_at: '2026-10-29T09:00:00Z', task: '' },
    { id: 8, scope: 'firm', status: 'pending', kind: 'missed', precheck_type: '', precheck_type_label: 'Every type of check', entity_type: 'trust',
      entity_label: 'Trust', rule: null, drafting: 'drafting', item: 'Trust deed', note: 'Ask for the trust deed and variations.', created_by: 'Sam',
      created_at: '2026-10-29T09:00:00Z', task: 'SMITH-3' },
  ],
})

describe('AI rules (AFIT, 29 Oct 2026)', () => {
  it('teaches the AI something it missed, for a type of check and an entity type', async () => {
    mocks.library = LIBRARY(true)
    render(<AiRulesPage />)
    await userEvent.click(screen.getByRole('button', { name: /Teach the AI/ }))
    const form = screen.getByRole('form', { name: 'New AI rule' })
    expect(within(form).getByRole('button', { name: 'Save rule' })).toBeDisabled()
    await userEvent.selectOptions(within(form).getByLabelText('Type of check'), 'residential_rental')
    await userEvent.selectOptions(within(form).getByLabelText('Entity type'), 'ltc')
    await userEvent.type(within(form).getByLabelText('Item (optional)'), 'Bond')
    await userEvent.type(within(form).getByLabelText(/What the AI should check or do/), 'Ask whether a tenancy bond was lodged.')
    await userEvent.click(within(form).getByRole('button', { name: 'Save rule' }))
    expect(mocks.add).toHaveBeenCalledWith(
      { kind: 'missed', item: 'Bond', note: 'Ask whether a tenancy bond was lodged.', precheck_type: 'residential_rental', entity_type: 'ltc' },
      expect.anything(),
    )
    expect(screen.queryByRole('form', { name: 'New AI rule' })).not.toBeInTheDocument()
  })

  it('shows each rule as the AI wrote it up, and a lead approves one waiting', async () => {
    mocks.library = LIBRARY(true)
    render(<AiRulesPage />)
    const rules = within(screen.getByRole('list', { name: 'Rules' })).getAllByRole('listitem')
    expect(rules[0]).toHaveTextContent('Landlord insurance')
    expect(rules[0]).toHaveTextContent('Residential rental')
    expect(rules[0]).toHaveTextContent('Ask for the landlord insurance schedule.')
    expect(rules[1]).toHaveTextContent('Waiting for approval')
    expect(rules[1]).toHaveTextContent('Trust')
    expect(rules[1]).toHaveTextContent('The AI is writing it up as a rule')
    await userEvent.click(within(rules[1]).getByRole('button', { name: 'Approve' }))
    expect(mocks.setStatus).toHaveBeenCalledWith({ id: 8, status: 'active' })
  })

  it('anyone else proposes a rule and cannot approve', async () => {
    mocks.library = LIBRARY(false)
    render(<AiRulesPage />)
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Teach the AI/ }))
    expect(screen.getByRole('button', { name: 'Propose rule' })).toBeInTheDocument()
    expect(screen.getByText(/A lead or an admin approves it before it applies/)).toBeInTheDocument()
  })

  it('filters by type of check', async () => {
    mocks.library = LIBRARY(true)
    mocks.filters = []
    render(<AiRulesPage />)
    await userEvent.selectOptions(screen.getAllByLabelText('Type of check')[0], 'investment')
    expect(mocks.filters.at(-1)).toEqual({ q: undefined, type: 'investment', status: undefined })
  })
})
