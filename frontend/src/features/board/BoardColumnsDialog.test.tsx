import { describe, expect, it } from 'vitest'

import { withColumn } from './BoardColumnsDialog'
import type { Board } from '@/api/types'

const board = {
  id: 1,
  column_config: [
    { name: 'To Start', status_ids: [1], wip_limit: null },
    { name: 'In Progress', status_ids: [2], wip_limit: null },
    { name: 'Complete', status_ids: [3], wip_limit: null },
  ],
  statuses: [
    { id: 1, name: 'To Start', category: 'todo' },
    { id: 2, name: 'In Progress', category: 'in_progress' },
    { id: 3, name: 'Complete', category: 'done' },
    { id: 9, name: 'Partner review', category: 'in_progress' },
  ],
} as unknown as Board

describe('withColumn', () => {
  it('adds a new stage after the chosen column', () => {
    const cols = withColumn(board, 'Waiting on bank', 'todo', 'In Progress')
    expect(cols.map((c) => c.name)).toEqual(['To Start', 'In Progress', 'Waiting on bank', 'Complete'])
    expect(cols[2]).toMatchObject({ status_ids: [], new_status: { category: 'todo' } })
  })

  it('reuses a stage the board already has a status for, and goes last when the place is not on this board', () => {
    const cols = withColumn(board, 'partner review', 'in_progress', 'Not here')
    expect(cols[3]).toEqual({ name: 'partner review', status_ids: [9], wip_limit: null })
  })
})
