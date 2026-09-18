import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Avatar } from './Avatar'

describe('Avatar', () => {
  it('renders the first letter of each word for a multi-word name', () => {
    render(<Avatar name="Hemanth Aviraj" />)
    expect(screen.getByText('HA')).toBeInTheDocument()
  })

  it('renders the first two letters for a single-word name', () => {
    render(<Avatar name="Cher" />)
    expect(screen.getByText('CH')).toBeInTheDocument()
  })

  it('renders an image instead of initials when a src is given', () => {
    render(<Avatar name="Hemanth Aviraj" src="https://example.com/avatar.png" />)
    const img = screen.getByRole('img', { name: 'Hemanth Aviraj' })
    expect(img).toHaveAttribute('src', 'https://example.com/avatar.png')
    expect(screen.queryByText('HA')).not.toBeInTheDocument()
  })
})
