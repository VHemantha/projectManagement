import { Check, Copy } from 'lucide-react'
import { type MouseEvent, useEffect, useState } from 'react'

import styles from './CopyButton.module.css'
import { Tooltip } from './Tooltip'

interface CopyButtonProps {
  /** The text placed on the clipboard when the button is pressed. */
  value: string
  /** What is being copied, used in the tooltip/aria-label (e.g. "email"). */
  label?: string
}

/**
 * A small "copy to clipboard" button with the familiar professional feedback:
 * the copy icon briefly becomes a tick and the tooltip reads "Copied!" for a
 * moment before returning to normal. Safe to place inside a clickable row — it
 * stops the click from bubbling up to the parent (e.g. a card that navigates).
 */
export function CopyButton({ value, label = 'to clipboard' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  // Reset the "copied" state after a short delay, cleaning up if the button
  // unmounts or is pressed again before the timer fires.
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])

  const handleCopy = async (event: MouseEvent) => {
    // Don't let the copy click trigger a surrounding clickable element.
    event.stopPropagation()
    event.preventDefault()
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      // Clipboard access can be blocked (e.g. insecure context); fail quietly.
    }
  }

  return (
    <Tooltip label={copied ? 'Copied!' : `Copy ${label}`}>
      <button type="button" className={styles.button} onClick={handleCopy} aria-label={`Copy ${label}`}>
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </Tooltip>
  )
}
