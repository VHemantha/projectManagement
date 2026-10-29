/** What a lesson or AI rule can be for (AFIT, 29 Oct 2026): a type of check and an entity type.
 * The server sends the same lists with the AI rules; these are the fallback and the form's order. */
export const CHECK_TYPES: { value: string; label: string }[] = [
  { value: '', label: 'Every type of check' },
  { value: 'residential_rental', label: 'Residential rental' },
  { value: 'general', label: 'General business' },
  { value: 'investment', label: 'Investment' },
]

export const RULE_ENTITY_TYPES: { value: string; label: string }[] = [
  { value: '', label: 'Any entity' },
  { value: 'trust', label: 'Trust' },
  { value: 'close_company', label: 'Close Company' },
  { value: 'ltc', label: 'LTC' },
  { value: 'sole_trader', label: 'Sole Trader' },
  { value: 'partnership', label: 'Partnership' },
  { value: 'body_corporate', label: 'Body Corporate' },
]

export const KIND_LABELS = {
  missed: 'Something it missed',
  not_needed: 'Something it asked for that is not needed',
  wrong_reason: 'A wrong reason',
  other: 'Other guidance',
} as const
