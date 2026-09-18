import * as RadixDialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import type { ReactNode } from 'react'

import styles from './Dialog.module.css'

export const Dialog = RadixDialog.Root
export const DialogTrigger = RadixDialog.Trigger

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
      <RadixDialog.Content className={styles.content} style={maxWidth ? { maxWidth } : undefined}>
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
