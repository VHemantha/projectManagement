import * as RadixTabs from '@radix-ui/react-tabs'
import type { CSSProperties, ReactNode } from 'react'

import styles from './Tabs.module.css'

export const Tabs = RadixTabs.Root

export function TabsList({ children, 'aria-label': ariaLabel }: { children: ReactNode; 'aria-label'?: string }) {
  return (
    <RadixTabs.List className={styles.list} aria-label={ariaLabel}>
      {children}
    </RadixTabs.List>
  )
}

export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  return (
    <RadixTabs.Trigger className={styles.trigger} value={value}>
      {children}
    </RadixTabs.Trigger>
  )
}

export function TabsContent({
  value,
  children,
  style,
  className,
}: {
  value: string
  children: ReactNode
  style?: CSSProperties
  className?: string
}) {
  return (
    <RadixTabs.Content className={className ?? styles.content} value={value} style={style}>
      {children}
    </RadixTabs.Content>
  )
}
