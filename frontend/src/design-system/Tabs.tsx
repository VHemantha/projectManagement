import * as RadixTabs from '@radix-ui/react-tabs'
import type { CSSProperties, ReactNode } from 'react'

import styles from './Tabs.module.css'

export const Tabs = RadixTabs.Root

export function TabsList({ children }: { children: ReactNode }) {
  return <RadixTabs.List className={styles.list}>{children}</RadixTabs.List>
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
}: {
  value: string
  children: ReactNode
  style?: CSSProperties
}) {
  return (
    <RadixTabs.Content className={styles.content} value={value} style={style}>
      {children}
    </RadixTabs.Content>
  )
}
