import { MessageSquare, User as UserIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import styles from './Avatar.module.css'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from './DropdownMenu'
import { useCreateDm } from '@/api/chat'
import { usePresenceStore } from '@/store/presenceStore'

const PALETTE = [
  '#0C66E4',
  '#36B37E',
  '#8777D9',
  '#E5493A',
  '#00B8D9',
  '#FF8B00',
  '#6554C0',
  '#1F845A',
]

function colorFor(seed: string) {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash)
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

interface AvatarProps {
  name: string
  src?: string | null
  size?: number
  /** When set, shows a small online/offline presence dot (from the app-wide presence socket
   * mounted in AppShell) in the corner. */
  userId?: number
  /** When set alongside userId, wraps the avatar in a click target offering Message / View
   * workload — the "click any user's avatar anywhere" quick-DM affordance. There's no
   * separate profile page in this app today (UserWorkloadPage at /people/:id already serves
   * as the profile view), so this offers one destination rather than two near-duplicates. */
  interactive?: boolean
}

function AvatarFace({ name, src, size }: { name: string; src?: string | null; size: number }) {
  const style = {
    width: size,
    height: size,
    fontSize: Math.max(10, size * 0.42),
    background: src ? undefined : colorFor(name || '?'),
  }
  return (
    <span className={styles.avatar} style={style} title={name}>
      {src ? <img className={styles.img} src={src} alt={name} /> : initials(name || '?')}
    </span>
  )
}

function PresenceFace({ name, src, size, userId }: { name: string; src?: string | null; size: number; userId?: number }) {
  const isOnline = usePresenceStore((s) => (userId != null ? s.onlineUserIds.has(userId) : false))
  return (
    <span style={{ position: 'relative', display: 'inline-flex' }}>
      <AvatarFace name={name} src={src} size={size} />
      {userId != null && (
        <span
          aria-hidden
          title={isOnline ? 'Online' : undefined}
          style={{
            position: 'absolute',
            bottom: -1,
            right: -1,
            width: Math.max(6, size * 0.28),
            height: Math.max(6, size * 0.28),
            borderRadius: '50%',
            background: isOnline ? 'var(--tf-success)' : 'transparent',
            border: isOnline ? '1.5px solid var(--tf-surface)' : 'none',
          }}
        />
      )}
    </span>
  )
}

/** Split out from Avatar so useNavigate/useCreateDm (both context-dependent — Router/
 * QueryClient) are only ever called when an avatar is actually rendered interactive. Every
 * non-interactive call site (still the majority) stays free of that dependency entirely. */
function InteractiveAvatar({ name, src, size, userId }: { name: string; src?: string | null; size: number; userId: number }) {
  const navigate = useNavigate()
  const createDm = useCreateDm()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', lineHeight: 0 }}
          aria-label={`${name} — actions`}
        >
          <PresenceFace name={name} src={src} size={size} userId={userId} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem
          onSelect={() =>
            createDm.mutate([userId], {
              onSuccess: (channel) => navigate(`/chat?channel=${channel.id}`),
            })
          }
        >
          <MessageSquare size={14} style={{ marginRight: 6 }} /> Message
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate(`/people/${userId}`)}>
          <UserIcon size={14} style={{ marginRight: 6 }} /> View workload
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function Avatar({ name, src, size = 24, userId, interactive }: AvatarProps) {
  if (interactive && userId != null) {
    return <InteractiveAvatar name={name} src={src} size={size} userId={userId} />
  }
  return <PresenceFace name={name} src={src} size={size} userId={userId} />
}
