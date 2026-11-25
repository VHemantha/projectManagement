import { Loader2, Mic, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { type VoiceLanguage, transcribeVoice } from '@/api/coordinator'
import { extractErrorMessage } from '@/api/errors'
import { Button } from '@/design-system'

const MAX_SECONDS = 120

/** Speak instead of typing (AFIT, 21 Nov 2026; for the agents' boxes from 25 Nov 2026): record in the browser, Amazon
 * Transcribe turns it into text, and the text goes into the box to check before it is sent - nothing is sent by voice
 * alone. Used only where speaking beats typing: the Practice Manager AI chat, the Local Tax story for a dummy trial
 * balance, questions to the job's assistant, corrections to the pre-check and special notes to the agents. */
export function VoiceButton({
  onText,
  label = 'Speak to the Practice Manager AI',
  title = 'Speak your message (Amazon Transcribe): it appears here to check before you send',
  language,
}: {
  onText: (text: string) => void
  /** What the button does, for screen readers ("Speak the story"). */
  label?: string
  title?: string
  language?: VoiceLanguage
}) {
  const [state, setState] = useState<'idle' | 'recording' | 'reading'>('idle')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const recorder = useRef<MediaRecorder | null>(null)
  const timer = useRef<number | null>(null)
  const supported = typeof window !== 'undefined' && typeof window.MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  useEffect(() => () => {
    if (timer.current) window.clearInterval(timer.current)
    recorder.current?.stream.getTracks().forEach((t) => t.stop())
  }, [])

  const stop = () => {
    if (timer.current) window.clearInterval(timer.current)
    if (recorder.current?.state === 'recording') recorder.current.stop()
  }

  const start = async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find((m) => MediaRecorder.isTypeSupported?.(m))
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      const chunks: Blob[] = []
      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setState('reading')
        try {
          const text = await transcribeVoice(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }), language)
          if (text) onText(text)
          else setError('No words were heard. Try again.')
        } catch (e) {
          setError(extractErrorMessage(e, 'The recording could not be turned into text.'))
        } finally {
          setState('idle')
        }
      }
      recorder.current = rec
      rec.start()
      setSeconds(0)
      setState('recording')
      timer.current = window.setInterval(() => setSeconds((s) => {
        if (s + 1 >= MAX_SECONDS) stop()
        return s + 1
      }), 1000)
    } catch {
      setError('The microphone could not be used. Allow it in the browser, or type instead.')
    }
  }

  if (!supported) return null
  return (
    <>
      {state === 'recording' ? (
        <Button type="button" variant="danger" size="sm" onClick={stop} aria-label="Stop recording">
          <Square size={12} /> {seconds}s
        </Button>
      ) : (
        <Button type="button" variant="subtle" size="sm" iconOnly onClick={start} disabled={state === 'reading'}
          aria-label={state === 'reading' ? 'Turning your recording into text' : label} title={title}>
          {state === 'reading' ? <Loader2 size={14} /> : <Mic size={14} />}
        </Button>
      )}
      {error && <span role="alert" style={{ fontSize: 12, color: 'var(--tf-danger)' }}>{error}</span>}
    </>
  )
}
