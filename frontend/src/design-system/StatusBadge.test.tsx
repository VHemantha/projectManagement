import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the label text', () => {
    render(<StatusBadge label="In Review" category="in_progress" />)
    expect(screen.getByText('In Review')).toBeInTheDocument()
  })

  it('uses the done-category color tokens', () => {
    render(<StatusBadge label="Done" category="done" />)
    const badge = screen.getByText('Done')
    expect(badge).toHaveStyle({ color: 'var(--tf-status-done-text)' })
  })
})
