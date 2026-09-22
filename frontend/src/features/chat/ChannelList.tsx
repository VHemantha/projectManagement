import { Hash, MessageSquarePlus, Plus } from 'lucide-react'
import { useState } from 'react'

import styles from './ChatPage.module.css'
import { channelDisplayName } from './channelDisplay'
import { CreateChannelDialog } from './CreateChannelDialog'
import { NewMessageDialog } from './NewMessageDialog'
import { useChannels } from '@/api/chat'
import type { Channel } from '@/api/types'
import { Avatar, Skeleton } from '@/design-system'
import { useAuthStore } from '@/store/authStore'
import { usePresenceStore } from '@/store/presenceStore'

interface ChannelListProps {
  selectedChannelId: number | null
  onSelect: (channel: Channel) => void
}

export function ChannelList({ selectedChannelId, onSelect }: ChannelListProps) {
  const currentUser = useAuthStore((s) => s.user)
  const onlineUserIds = usePresenceStore((s) => s.onlineUserIds)
  const { data: channels, isLoading } = useChannels()
  const [createOpen, setCreateOpen] = useState(false)
  const [newMessageOpen, setNewMessageOpen] = useState(false)

  const general = channels?.filter((c) => c.channel_type === 'general') ?? []
  const project = channels?.filter((c) => c.channel_type === 'project') ?? []
  const team = channels?.filter((c) => c.channel_type === 'team') ?? []
  const topic = channels?.filter((c) => c.channel_type === 'topic') ?? []
  // Keep empty DMs (no messages sent yet) out of the list — except the one currently open,
  // so starting a new conversation doesn't make it vanish from under you before you've typed
  // anything (see NewMessageDialog / ChannelSerializer.get_has_messages).
  const directMessages =
    channels?.filter(
      (c) =>
        (c.channel_type === 'direct_message' || c.channel_type === 'group_dm') &&
        (c.has_messages || c.id === selectedChannelId),
    ) ?? []

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

  const renderDmGroup = () =>
    directMessages.length > 0 && (
      <div>
        <div className={styles.channelGroupLabel}>Direct messages</div>
        {directMessages.map((channel) => {
          const others = channel.participants.filter((p) => p.id !== currentUser?.id)
          const isOnline = others.length === 1 && onlineUserIds.has(others[0].id)
          return (
            <div
              key={channel.id}
              className={`${styles.channelRow} ${selectedChannelId === channel.id ? styles.active : ''} ${
                channel.unread_count > 0 ? styles.unread : ''
              }`}
              onClick={() => onSelect(channel)}
            >
              {others.length === 1 ? (
                <Avatar name={others[0].display_name} src={others[0].avatar} size={18} userId={others[0].id} />
              ) : (
                <MessageSquarePlus size={13} />
              )}
              <span className={styles.channelName}>{channelDisplayName(channel, currentUser?.id)}</span>
              {isOnline && (
                <span
                  aria-hidden
                  style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--tf-success)' }}
                />
              )}
              {channel.unread_count > 0 && <span className={styles.unreadBadge}>{channel.unread_count}</span>}
            </div>
          )
        })}
      </div>
    )

  return (
    <aside className={styles.sidebar}>
      <div className={styles.sidebarHeader}>
        <span className={styles.sidebarTitle}>Chat</span>
        <button
          onClick={() => setNewMessageOpen(true)}
          aria-label="New message"
          title="New message"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--tf-text-subtle)' }}
        >
          <MessageSquarePlus size={16} />
        </button>
        <button
          onClick={() => setCreateOpen(true)}
          aria-label="Create channel"
          title="Create channel"
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
            {renderDmGroup()}
            {renderGroup('Channels', topic)}
            {!channels?.length && <div className={styles.empty}>No channels yet.</div>}
          </>
        )}
      </div>
      <CreateChannelDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={onSelect} />
      <NewMessageDialog open={newMessageOpen} onOpenChange={setNewMessageOpen} onCreated={onSelect} />
    </aside>
  )
}
