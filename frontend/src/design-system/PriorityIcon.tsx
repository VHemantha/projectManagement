import { ChevronDown, ChevronsDown, ChevronsUp, ChevronUp, Equal } from 'lucide-react'

export type Priority = 'highest' | 'high' | 'medium' | 'low' | 'lowest'

const CONFIG: Record<Priority, { icon: typeof ChevronsUp; color: string; label: string }> = {
  highest: { icon: ChevronsUp, color: 'var(--tf-priority-highest)', label: 'Highest' },
  high: { icon: ChevronUp, color: 'var(--tf-priority-high)', label: 'High' },
  medium: { icon: Equal, color: 'var(--tf-priority-medium)', label: 'Medium' },
  low: { icon: ChevronDown, color: 'var(--tf-priority-low)', label: 'Low' },
  lowest: { icon: ChevronsDown, color: 'var(--tf-priority-lowest)', label: 'Lowest' },
}

interface PriorityIconProps {
  priority: Priority
  size?: number
}

export function PriorityIcon({ priority, size = 16 }: PriorityIconProps) {
  const { icon: Icon, color, label } = CONFIG[priority]
  return <Icon size={size} color={color} strokeWidth={2.5} aria-label={label} />
}
