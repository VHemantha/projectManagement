import { Hash, Plus } from 'lucide-react'
import { useState } from 'react'

import styles from './ChatPage.module.css'
import { CreateChannelDialog } from './CreateChannelDialog'
import { useChannels } from '@/api/chat'
import type { Channel } from '@/api/types'
import { Skeleton } from '@/design-system'

interface ChannelListProps {
  selectedChannelId: number | null
  onSelect: (channel: Channel) => void
}

export function ChannelList({ selectedChannelId, onSelect }: ChannelListProps) {
  const { data: channels, isLoading } = useChannels()
  const [createOpen, setCreateOpen] = useState(false)

  const general = channels?.filter((c) => c.channel_type === 'general') ?? []
  const project = channels?.filter((c) => c.channel_type === 'project') ?? []
  const team = channels?.filter((c) => c.channel_type === 'team') ?? []
  const topic = channels?.filter((c) => c.channel_type === 'topic') ?? []

  const renderGroup = (label: string, items: Channel[]) =>
    items.length > 0 && (
      <div key={label}>
        <div className={styles.channelGroupLabel}>{label}</div>
        {items.map((channel) => (
          <div
            key={channel.id}
            className={`${styles.channelRow} ${selectedChannelId === channel.id ? styles.active : ''} ${
              channel.unread_count > 0 ? styles.unread : ''
            }`}
            onClick={() => onSelect(channel)}
          >
            <Hash size={13} />
            <span className={styles.channelName}>{channel.name}</span>
            {channel.unread_count > 0 && <span className={styles.unreadBadge}>{channel.unread_count}</span>}
          </div>
        ))}
      </div>
    )

  return (
    <aside className={styles.sidebar}>
      <div className={styles.sidebarHeader}>
        <span className={styles.sidebarTitle}>Chat</span>
        <button
          onClick={() => setCreateOpen(true)}
          aria-label="Create channel"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--tf-text-subtle)' }}
        >
          <Plus size={16} />
        </button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '10px 12px' }}>
            {[0, 1, 2, 3, 4].map((row) => (
              <Skeleton key={row} height={13} width={row % 2 === 0 ? '70%' : '55%'} />
            ))}
          </div>
        ) : (
          <>
            {renderGroup('General', general)}
            {renderGroup('Projects', project)}
            {renderGroup('Teams', team)}
            {renderGroup('Channels', topic)}
            {!channels?.length && <div className={styles.empty}>No channels yet.</div>}
          </>
        )}
      </div>
      <CreateChannelDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={onSelect} />
    </aside>
  )
}
