import { Bookmark, Bug, CheckSquare, Zap } from 'lucide-react'

const CONFIG: Record<string, { icon: typeof Zap; color: string }> = {
  Epic: { icon: Zap, color: 'var(--tf-type-epic)' },
  Story: { icon: Bookmark, color: 'var(--tf-type-story)' },
  Task: { icon: CheckSquare, color: 'var(--tf-type-task)' },
  Bug: { icon: Bug, color: 'var(--tf-type-bug)' },
  'Sub-task': { icon: CheckSquare, color: 'var(--tf-type-subtask)' },
}

interface IssueTypeIconProps {
  typeName: string
  size?: number
}

export function IssueTypeIcon({ typeName, size = 16 }: IssueTypeIconProps) {
  const cfg = CONFIG[typeName] ?? CONFIG.Task
  const Icon = cfg.icon
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size + 2,
        height: size + 2,
        borderRadius: 3,
        background: cfg.color,
        flexShrink: 0,
      }}
      title={typeName}
    >
      <Icon size={size - 3} color="#fff" strokeWidth={2.5} fill={typeName === 'Story' ? '#fff' : 'none'} />
    </span>
  )
}
