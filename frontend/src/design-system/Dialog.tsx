import * as RadixDialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

import styles from './Dialog.module.css'

export const Dialog = RadixDialog.Root
export const DialogTrigger = RadixDialog.Trigger

/** For a window's onEscapeKeyDown: Escape that closes an open dropdown list must not close the
 * window too. With the styled dropdowns (global.css) the browser no longer swallows that Escape. */
export function keepOpenForSelect(event: KeyboardEvent) {
  // While the list is open the highlighted <option> has the focus, so look up its <select>.
  const target = event.target
  const select = target instanceof Element ? target.closest('select') : null
  if (!select) return
  try {
    if (select.matches(':open')) event.preventDefault()
  } catch {
    // A browser without :open also has no styled dropdowns: its own list takes the Escape.
  }
}

interface DialogContentProps {
  children: ReactNode
  title: string
  maxWidth?: number
  hideTitle?: boolean
}

export function DialogContent({ children, title, maxWidth, hideTitle }: DialogContentProps) {
  return (
    <RadixDialog.Portal>
      <RadixDialog.Overlay className={styles.overlay} />
      <RadixDialog.Content
        className={styles.content}
        style={maxWidth ? { maxWidth } : undefined}
        onEscapeKeyDown={keepOpenForSelect}
      >
        <div className={styles.header}>
          <RadixDialog.Title
            className={styles.title}
            style={hideTitle ? { position: 'absolute', width: 1, height: 1, overflow: 'hidden' } : undefined}
          >
            {title}
          </RadixDialog.Title>
          <RadixDialog.Close className={styles.closeBtn} aria-label="Close">
            <X size={18} />
          </RadixDialog.Close>
        </div>
        {children}
      </RadixDialog.Content>
    </RadixDialog.Portal>
  )
}
