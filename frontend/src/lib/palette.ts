/**
 * Palette colours needed as hex in code: colour pickers (<input type="color">), colours saved
 * on columns/labels/cards, and generated avatars. They mirror the CSS tokens in
 * src/design-system/tokens.css — change both together.
 */

/** Generated avatar backgrounds: white initials pass WCAG AA on each. */
export const AVATAR_COLORS = ['#6a3df0', '#1d4ed8', '#0f766e', '#c2410c', '#be185d', '#15803d', '#5b2fd6', '#b42318']

/** Solid accents (--tf-solid-*): column stripes, dots, card accents. */
export const SOLID = {
  grey: '#7a7891',
  blue: '#3b6ff5',
  violet: '#7b5cff',
  orange: '#e2620c',
  pink: '#e0457b',
  green: '#1f9d63',
  teal: '#0e8f80',
} as const

/** Colour choices offered for board columns. */
export const COLUMN_SWATCHES = [SOLID.grey, SOLID.blue, SOLID.violet, SOLID.orange, SOLID.pink, SOLID.green, SOLID.teal]

/** Default colours for the standard columns; any other column takes the next colour in order. */
const COLUMN_DEFAULTS: Record<string, string> = {
  backlog: SOLID.grey,
  'to do': SOLID.blue,
  'in progress': SOLID.violet,
  'in review': SOLID.orange,
  blocked: SOLID.pink,
  done: SOLID.green,
}

const COLUMN_SEQUENCE = [SOLID.grey, SOLID.blue, SOLID.violet, SOLID.orange, SOLID.teal, SOLID.pink, SOLID.green]

/** A column's colour when none was chosen: by its standard name, else by position, so every
 * column is distinct and the board reads left to right in the same order everywhere. */
export function defaultColumnColor(name: string, index: number): string {
  return COLUMN_DEFAULTS[name.trim().toLowerCase()] ?? COLUMN_SEQUENCE[index % COLUMN_SEQUENCE.length]
}

/** Light label backgrounds (dark text on each). */
export const LABEL_COLORS = ['#ecebf2', '#efebff', '#dbeafe', '#ccfbf1', '#dcfce7', '#ffedd5', '#fce7f3', '#fef3c7']

/** Epics without their own colour. */
export const DEFAULT_EPIC_COLOR = SOLID.violet

/** Card accent defaults by priority (mirrors --tf-priority-*). */
export const PRIORITY_COLORS = {
  highest: '#d92d20',
  high: '#e8590c',
  medium: '#d9a206',
  low: '#3b6ff5',
  lowest: '#3b6ff5',
} as const

/** Card accent defaults by due date. */
export const DUE_DATE_COLORS = { overdue: '#e0453c', due_soon: '#e0a106', on_track: SOLID.green } as const
