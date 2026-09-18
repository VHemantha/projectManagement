import { formatDistanceToNow } from 'date-fns'
import { CornerUpRight, Link2, Paperclip, Plus, Smile } from 'lucide-react'
import { useState } from 'react'

import styles from './ChatPage.module.css'
import { CreateTaskFromMessageDialog } from './CreateTaskFromMessageDialog'
import { LinkTaskToMessageDialog } from './LinkTaskToMessageDialog'
import { useToggleReaction } from '@/api/chat'
import type { ChatMessage } from '@/api/types'
import { Avatar, IssueKey, RichTextEditor } from '@/design-system'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'

const QUICK_EMOJIS = ['👍', '🎉', '✅', '👀']

interface MessageBubbleProps {
  message: ChatMessage
  channelId: number
  onOpenThread?: (message: ChatMessage) => void
}

export function MessageBubble({ message, channelId, onOpenThread }: MessageBubbleProps) {
  const currentUser = useAuthStore((s) => s.user)
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const toggleReaction = useToggleReaction(channelId)
  const [createTaskOpen, setCreateTaskOpen] = useState(false)
  const [linkTaskOpen, setLinkTaskOpen] = useState(false)
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false)

  if (message.is_system) {
    return (
      <div className={styles.messageRow}>
        <span className={styles.systemMessage}>
          <RichTextEditor content={message.body} editable={false} showToolbar={false} />
        </span>
      </div>
    )
  }

  const myReactionEmojis = new Set(
    message.reactions.filter((r) => r.user.id === currentUser?.id).map((r) => r.emoji),
  )

  const reactionsByEmoji = new Map<string, number>()
  for (const r of message.reactions) reactionsByEmoji.set(r.emoji, (reactionsByEmoji.get(r.emoji) ?? 0) + 1)

  return (
    <div className={styles.messageRow}>
      <Avatar name={message.author.display_name} src={message.author.avatar} size={32} />
      <div className={styles.messageBody}>
        <div className={styles.messageMeta}>
          <span className={styles.messageAuthor}>{message.author.display_name}</span>
          <span className={styles.messageTime}>
            {message._pending
              ? 'sending…'
              : formatDistanceToNow(new Date(message.created_at), { addSuffix: true })}
          </span>
        </div>
        <RichTextEditor content={message.body} editable={false} showToolbar={false} />

        {message.attachments.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
            {message.attachments.map((att) => (
              <a
                key={att.id}
                href={att.file}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 12,
                  color: 'var(--tf-text-link)',
                }}
              >
                <Paperclip size={12} /> {att.filename}
              </a>
            ))}
          </div>
        )}

        {message.issue_links.length > 0 && (
          <div>
            {message.issue_links.map((link) => (
              <span
                key={link.id}
                className={styles.taskChip}
                onClick={() => openIssueModal(link.issue.key)}
              >
                <IssueKey value={link.issue.key} /> {link.issue.summary}
              </span>
            ))}
          </div>
        )}

        {message.reactions.length > 0 && (
          <div className={styles.reactionRow}>
            {[...reactionsByEmoji.entries()].map(([emoji, count]) => (
              <span
                key={emoji}
                className={`${styles.reactionChip} ${myReactionEmojis.has(emoji) ? styles.mine : ''}`}
                onClick={() =>
                  toggleReaction.mutate({ messageId: message.id, emoji, add: !myReactionEmojis.has(emoji) })
                }
              >
                {emoji} {count}
              </span>
            ))}
          </div>
        )}

        {message.reply_count > 0 && onOpenThread && (
          <div
            style={{ fontSize: 12, color: 'var(--tf-text-link)', cursor: 'pointer', marginTop: 4 }}
            onClick={() => onOpenThread(message)}
          >
            {message.reply_count} {message.reply_count === 1 ? 'reply' : 'replies'}
          </div>
        )}
      </div>

      {!message._pending && (
        <div className={styles.messageHoverActions}>
          <button
            title="React"
            onClick={() => setEmojiPickerOpen((v) => !v)}
            style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 4 }}
          >
            <Smile size={14} />
          </button>
          {onOpenThread && (
            <button
              title="Reply in thread"
              onClick={() => onOpenThread(message)}
              style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 4 }}
            >
              <CornerUpRight size={14} />
            </button>
          )}
          <button
            title="Create task from message"
            onClick={() => setCreateTaskOpen(true)}
            style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 4 }}
          >
            <Plus size={14} />
          </button>
          <button
            title="Link to existing task"
            onClick={() => setLinkTaskOpen(true)}
            style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 4 }}
          >
            <Link2 size={14} />
          </button>
        </div>
      )}

      {emojiPickerOpen && (
        <div
          style={{
            position: 'absolute',
            top: -16,
            right: 90,
            background: 'var(--tf-surface)',
            border: '1px solid var(--tf-border)',
            borderRadius: 6,
            padding: 4,
            display: 'flex',
            gap: 2,
            boxShadow: 'var(--tf-shadow-sm)',
          }}
        >
          {QUICK_EMOJIS.map((emoji) => (
            <button
              key={emoji}
              onClick={() => {
                toggleReaction.mutate({ messageId: message.id, emoji, add: !myReactionEmojis.has(emoji) })
                setEmojiPickerOpen(false)
              }}
              style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 16, padding: 2 }}
            >
              {emoji}
            </button>
          ))}
        </div>
      )}

      <CreateTaskFromMessageDialog message={message} open={createTaskOpen} onOpenChange={setCreateTaskOpen} />
      <LinkTaskToMessageDialog message={message} open={linkTaskOpen} onOpenChange={setLinkTaskOpen} />
    </div>
  )
}
