import type { NoteAgent } from '@/api/precheck'

/** The AI agents a special note can be for (AFIT, 13 Nov 2026); none ticked = every agent. */
export const NOTE_AGENTS: { value: NoteAgent; label: string }[] = [
  { value: 'precheck', label: 'Pre-check' },
  { value: 'guide', label: 'Preparation guide' },
  { value: 'review', label: 'Review' },
  { value: 'ask', label: 'Ask' },
]
