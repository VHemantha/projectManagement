/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { AVATAR_COLORS, COLUMN_SWATCHES, defaultColumnColor, SOLID } from '@/lib/palette'

// Read from disk (tests run from frontend/): Vitest doesn't load CSS contents into modules.
const tokensCss = readFileSync(resolve(process.cwd(), 'src/design-system/tokens.css'), 'utf8')

/** Resolve a token to its hex value (following var() aliases). */
function token(name: string): string {
  const match = tokensCss.match(new RegExp(`--${name}:\\s*([^;]+);`))
  if (!match) throw new Error(`No token --${name}`)
  const value = match[1].trim()
  const alias = value.match(/^var\(--([\w-]+)\)$/)
  return alias ? token(alias[1]) : value
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const AA_TEXT = 4.5
const AA_UI = 3

describe('colour tokens meet WCAG AA', () => {
  it.each([
    ['tf-text', 'tf-bg'],
    ['tf-text-secondary', 'tf-surface-hover'],
    ['tf-text-subtle', 'tf-surface'],
    ['tf-text-subtle', 'tf-bg'],
    ['tf-text-subtle', 'tf-surface-hover'],
    ['tf-text-inverse', 'tf-primary'],
    ['tf-text-inverse', 'tf-primary-hover'],
    ['tf-text-inverse', 'tf-inverse-bg'],
    ['tf-primary', 'tf-surface'],
    ['tf-primary', 'tf-bg'],
    ['tf-primary-strong', 'tf-primary-subtle'],
    ['tf-status-todo-text', 'tf-status-todo-bg'],
    ['tf-status-inprogress-text', 'tf-status-inprogress-bg'],
    ['tf-status-done-text', 'tf-status-done-bg'],
    ['tf-danger', 'tf-danger-bg'],
    ['tf-danger', 'tf-danger-bg-hover'],
    ['tf-warning-text', 'tf-warning-bg'],
    ['tf-success', 'tf-success-bg'],
    ['tf-accent-violet', 'tf-accent-violet-bg'],
    ['tf-accent-pink', 'tf-accent-pink-bg'],
    ['tf-accent-blue', 'tf-accent-blue-bg'],
    ['tf-accent-teal', 'tf-accent-teal-bg'],
    ['tf-accent-orange', 'tf-accent-orange-bg'],
    ['tf-accent-green', 'tf-accent-green-bg'],
  ])('%s on %s is readable text', (fg, bg) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(AA_TEXT)
  })

  it.each(['grey', 'blue', 'violet', 'orange', 'pink', 'green', 'teal'])('solid %s stands out from white', (name) => {
    const value = token(`tf-solid-${name}`)
    expect(contrast(value, '#ffffff')).toBeGreaterThanOrEqual(AA_UI)
    expect(SOLID[name as keyof typeof SOLID]).toBe(value) // palette.ts mirrors the tokens
  })

  it('white avatar initials are readable on every avatar colour', () => {
    for (const color of AVATAR_COLORS) expect(contrast('#ffffff', color)).toBeGreaterThanOrEqual(AA_TEXT)
  })
})

describe('default Kanban column colours', () => {
  it('are distinct, in column order', () => {
    const names = ['Backlog', 'To do', 'In progress', 'In review', 'Blocked', 'Done']
    const colors = names.map((n, i) => defaultColumnColor(n, i))
    expect(new Set(colors).size).toBe(names.length)
    expect(colors[0]).toBe(SOLID.grey)
    expect(colors[5]).toBe(SOLID.green)
    // Unknown names follow the sequence by position.
    expect(defaultColumnColor('QA', 4)).toBe(defaultColumnColor('Anything', 4))
    expect(COLUMN_SWATCHES).toContain(defaultColumnColor('QA', 4))
  })
})
