import { Loader2, Mic, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { transcribeVoice } from '@/api/coordinator'
import { extractErrorMessage } from '@/api/errors'
import { Button } from '@/design-system'

const MAX_SECONDS = 120

/** Speak to the Practice Manager AI (AFIT, 21 Nov 2026): record in the browser, Amazon Transcribe turns it into
 * text, and the text goes into the message box to check and send - "create a job for ..." works as typed. */
export function VoiceButton({ onText }: { onText: (text: string) => void }) {
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
          const text = await transcribeVoice(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }))
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
      setError('The microphone could not be used. Allow it in the browser, or type your message.')
    }
  }

  if (!supported) return null
  return (
    <>
      {state === 'recording' ? (
        <Button variant="danger" size="sm" onClick={stop} aria-label="Stop recording">
          <Square size={12} /> {seconds}s
        </Button>
      ) : (
        <Button variant="subtle" size="sm" iconOnly onClick={start} disabled={state === 'reading'}
          aria-label={state === 'reading' ? 'Turning your recording into text' : 'Speak to the Practice Manager AI'}
          title="Speak your message (Amazon Transcribe): it appears here to check before you send">
          {state === 'reading' ? <Loader2 size={14} /> : <Mic size={14} />}
        </Button>
      )}
      {error && <span role="alert" style={{ fontSize: 12, color: 'var(--tf-danger)' }}>{error}</span>}
    </>
  )
}
