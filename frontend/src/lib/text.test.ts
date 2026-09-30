import { describe, expect, it } from 'vitest'

import { sentenceCase } from './text'

describe('sentenceCase', () => {
  it('capitalises only the first letter and turns underscores into spaces', () => {
    expect(sentenceCase('in_progress')).toBe('In progress')
    expect(sentenceCase('relates to')).toBe('Relates to')
    expect(sentenceCase('scrum project')).toBe('Scrum project')
    expect(sentenceCase('API key')).toBe('API key')
    expect(sentenceCase('')).toBe('')
  })
})
