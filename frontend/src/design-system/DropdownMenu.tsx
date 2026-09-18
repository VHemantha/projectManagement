import * as RadixDropdown from '@radix-ui/react-dropdown-menu'
import type { ReactNode } from 'react'

import styles from './DropdownMenu.module.css'

export const DropdownMenu = RadixDropdown.Root
export const DropdownMenuTrigger = RadixDropdown.Trigger

export function DropdownMenuContent({
  children,
  align = 'end',
}: {
  children: ReactNode
  align?: 'start' | 'end' | 'center'
}) {
  return (
    <RadixDropdown.Portal>
      <RadixDropdown.Content className={styles.content} align={align} sideOffset={6}>
        {children}
      </RadixDropdown.Content>
    </RadixDropdown.Portal>
  )
}

export function DropdownMenuItem({
  children,
  onSelect,
  disabled,
}: {
  children: ReactNode
  onSelect?: () => void
  disabled?: boolean
}) {
  return (
    <RadixDropdown.Item className={styles.item} onSelect={onSelect} disabled={disabled}>
      {children}
    </RadixDropdown.Item>
  )
}

export function DropdownMenuSeparator() {
  return <RadixDropdown.Separator className={styles.separator} />
}

export function DropdownMenuLabel({ children }: { children: ReactNode }) {
  return <RadixDropdown.Label className={styles.label}>{children}</RadixDropdown.Label>
}
