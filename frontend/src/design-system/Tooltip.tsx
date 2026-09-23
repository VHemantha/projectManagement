import * as RadixTooltip from '@radix-ui/react-tooltip'
import type { ReactElement, ReactNode } from 'react'

import styles from './Tooltip.module.css'

/**
 * Wraps the app once so every tooltip shares one timing context: after the first
 * hint appears, moving to a neighbouring control shows its hint instantly rather
 * than waiting out the open delay again (the familiar toolbar behaviour).
 */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <RadixTooltip.Provider delayDuration={300} skipDelayDuration={200}>
      {children}
    </RadixTooltip.Provider>
  )
}

interface TooltipProps {
  /** Short hint shown on hover/focus. When empty the child is rendered untouched. */
  label: ReactNode
  /** The control the hint describes — a single element (button, link, ...). */
  children: ReactElement
  /** Which side of the control the hint pops out on. */
  side?: 'top' | 'right' | 'bottom' | 'left'
}

/**
 * A small hover/focus hint for a control. Uses Radix's `asChild` so it adds no
 * wrapper element of its own — the child stays exactly what it was and simply
 * gains a tooltip. Passing an empty `label` disables it, which lets callers turn
 * the hint off in contexts where the control already shows its own text (e.g. an
 * expanded sidebar item).
 */
export function Tooltip({ label, children, side = 'bottom' }: TooltipProps) {
  if (!label) return children

  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content className={styles.content} side={side} sideOffset={6}>
          {label}
          <RadixTooltip.Arrow className={styles.arrow} />
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  )
}
