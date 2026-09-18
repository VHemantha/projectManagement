import { useEffect, useRef, useState } from 'react'

import styles from './ChatPage.module.css'
import { MessageBubble } from './MessageBubble'
import { MessageComposer } from './MessageComposer'
import { useMarkChannelRead, useMessages, useThreadReplies } from '@/api/chat'
import { useChatSocket } from '@/api/useChatSocket'
import type { Channel, ChatMessage } from '@/api/types'
import { Skeleton } from '@/design-system'

function ThreadPanel({ parent, channel, onClose }: { parent: ChatMessage; channel: Channel; onClose: () => void }) {
  const { data: replies } = useThreadReplies(parent.id)
  const { sendMessage } = useChatSocket(channel.id)

  return (
    <div style={{ width: 340, flexShrink: 0, borderLeft: '1px solid var(--tf-border)', display: 'flex', flexDirection: 'column' }}>
      <div className={styles.threadHeader}>
        <span className={styles.threadTitle}>Thread</span>
        <button onClick={onClose} style={{ marginLeft: 'auto', border: 'none', background: 'none', cursor: 'pointer' }}>
          ✕
        </button>
      </div>
      <div className={styles.messages}>
        <MessageBubble message={parent} channelId={channel.id} />
        <div style={{ borderTop: '1px solid var(--tf-border)', margin: '4px 0' }} />
        {replies?.map((reply) => (
          <MessageBubble key={reply.id} message={reply} channelId={channel.id} />
        ))}
      </div>
      <MessageComposer
        channel={channel}
        onSend={(body, mentioned) => sendMessage(body, parent.id, mentioned)}
      />
    </div>
  )
}

export function MessageThread({ channel }: { channel: Channel }) {
  const { data: messages, isLoading } = useMessages(channel.id)
  const { sendMessage, sendTyping, typingUser, connectionState } = useChatSocket(channel.id)
  const markRead = useMarkChannelRead()
  const scrollRef = useRef<HTMLDivElement>(null)
  const [threadParent, setThreadParent] = useState<ChatMessage | null>(null)

  useEffect(() => {
    markRead.mutate(channel.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel.id])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages?.length])

  return (
    <div style={{ display: 'flex', flex: 1, minWidth: 0 }}>
      <div className={styles.thread}>
        <div className={styles.threadHeader}>
          <div>
            <div className={styles.threadTitle}>#{channel.name}</div>
            {channel.description && <div className={styles.threadDescription}>{channel.description}</div>}
          </div>
          <span
            className={styles.connectionDot}
            title={connectionState}
            style={{
              background:
                connectionState === 'open'
                  ? 'var(--tf-success)'
                  : connectionState === 'connecting'
                    ? 'var(--tf-warning)'
                    : 'var(--tf-danger)',
            }}
          />
        </div>

        <div className={styles.messages} ref={scrollRef}>
          {isLoading ? (
            <>
              <Skeleton height={40} />
              <Skeleton height={40} />
              <Skeleton height={40} />
            </>
          ) : !messages || messages.length === 0 ? (
            <div className={styles.empty}>No messages yet. Say hello 👋</div>
          ) : (
            messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                channelId={channel.id}
                onOpenThread={setThreadParent}
              />
            ))
          )}
        </div>
        <div className={styles.typingIndicator}>{typingUser && `${typingUser.displayName} is typing…`}</div>

        <MessageComposer
          channel={channel}
          onSend={(body, mentioned) => {
            sendMessage(body, undefined, mentioned)
            markRead.mutate(channel.id)
          }}
          onTyping={sendTyping}
        />
      </div>
      {threadParent && <ThreadPanel parent={threadParent} channel={channel} onClose={() => setThreadParent(null)} />}
    </div>
  )
}
