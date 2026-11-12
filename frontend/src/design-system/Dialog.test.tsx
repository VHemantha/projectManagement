import { describe, expect, it, vi } from 'vitest'

import { keepOpenForSelect } from './Dialog'

/** An Escape keydown from `target`, with the dropdown's :open state as given. */
function escapeFrom(target: Element, open: boolean) {
  const select = target.closest('select')
  if (select) select.matches = (q: string) => (q === ':open' ? open : Element.prototype.matches.call(select, q))
  const event = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true })
  Object.defineProperty(event, 'target', { value: target })
  const prevent = vi.spyOn(event, 'preventDefault')
  keepOpenForSelect(event)
  return prevent.mock.calls.length > 0
}

describe('Escape in a window with styled dropdowns', () => {
  it('closes only the open list (the highlighted option has the focus), not the window', () => {
    const select = document.createElement('select')
    const option = document.createElement('option')
    select.append(option)
    expect(escapeFrom(option, true)).toBe(true)
    expect(escapeFrom(select, true)).toBe(true)
  })

  it('closes the window as usual when no list is open', () => {
    const select = document.createElement('select')
    select.append(document.createElement('option'))
    expect(escapeFrom(select, false)).toBe(false)
    expect(escapeFrom(document.createElement('input'), false)).toBe(false)
  })
})
