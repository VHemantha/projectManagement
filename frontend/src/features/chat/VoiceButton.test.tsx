import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AxiosError, type AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { withSpoken } from '@/api/coordinator'
import type { LocalTaxState } from '@/api/localTax'
import { StoryTrialBalance } from '@/features/localtax/TbSources'
import { SpecialNotes } from '@/features/precheck/SpecialNotes'

const m = vi.hoisted(() => ({ transcribe: vi.fn(), idle: () => ({ mutate: vi.fn(), isPending: false, isError: false, error: null }) }))
vi.mock('@/api/coordinator', async (orig) => ({ ...(await orig<typeof import('@/api/coordinator')>()), transcribeVoice: m.transcribe }))
vi.mock('@/api/localTax', async (orig) => ({ ...(await orig<typeof import('@/api/localTax')>()), useTbStory: m.idle, useUseStoryTb: m.idle }))
vi.mock('@/api/precheck', async (orig) => ({
  ...(await orig<typeof import('@/api/precheck')>()),
  useAgentNotes: () => ({ data: { notes: [], limit: 20 }, isLoading: false }), useAddAgentNote: m.idle, useRemoveAgentNote: m.idle,
}))

/** A browser with a microphone: the recording is a fake clip, handed over when it stops. */
class FakeRecorder {
  static isTypeSupported = () => true
  state = 'inactive'
  mimeType = 'audio/webm'
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  stream: MediaStream
  constructor(stream: MediaStream) {
    this.stream = stream
  }
  start() { this.state = 'recording' }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['clip'], { type: 'audio/webm' }) })
    this.onstop?.()
  }
}

const state = { engagement: { data: {} } } as unknown as LocalTaxState

describe('speaking to the agents (AFIT, 25 Nov 2026)', () => {
  beforeEach(() => {
    m.transcribe.mockReset()
    vi.stubGlobal('MediaRecorder', FakeRecorder)
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true, value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) },
    })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('adds spoken words after what is typed', () => {
    expect(withSpoken('', 'A bakery')).toBe('A bakery')
    expect(withSpoken('A bakery in Kandy.  ', 'Sales of 30 million.')).toBe('A bakery in Kandy. Sales of 30 million.')
  })

  it('tells the Local Tax story by voice, in Indian English, into the box to check before the trial balance is made', async () => {
    m.transcribe.mockResolvedValue('Sales of about LKR 30 million, up 15 percent.')
    render(<StoryTrialBalance taskKey="LOC-1" state={state} />)
    const box = screen.getByRole('textbox', { name: 'The story' })
    await userEvent.type(box, 'A family bakery in Kandy.')
    await userEvent.click(screen.getByRole('button', { name: 'Speak the story' }))
    await userEvent.click(screen.getByRole('button', { name: 'Stop recording' }))
    await waitFor(() => expect(box).toHaveValue('A family bakery in Kandy. Sales of about LKR 30 million, up 15 percent.'))
    expect(m.transcribe.mock.calls[0][1]).toBe('en-IN')
  })

  it('says a special note for the agents (New Zealand English), and shows why when it cannot be read', async () => {
    m.transcribe.mockResolvedValueOnce('The client sold the rental in June.').mockRejectedValueOnce(
      new AxiosError('503', '503', undefined, undefined, { status: 503, data: { detail: "Amazon Transcribe isn't switched on for the firm's AWS account yet. Type it instead." } } as AxiosResponse))
    render(<SpecialNotes jobKey="RWCA-1" />)
    await userEvent.click(screen.getByRole('button', { name: 'Speak the note' }))
    await userEvent.click(screen.getByRole('button', { name: 'Stop recording' }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'New note for the AI' })).toHaveValue('The client sold the rental in June.'))
    expect(m.transcribe.mock.calls[0][1]).toBeUndefined()  // the server's default: New Zealand English
    await userEvent.click(screen.getByRole('button', { name: 'Speak the note' }))
    await userEvent.click(screen.getByRole('button', { name: 'Stop recording' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/isn't switched on/)
  })
})
