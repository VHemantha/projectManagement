import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import styles from './ChatPage.module.css'
import { ChannelList } from './ChannelList'
import { MessageThread } from './MessageThread'
import { useChannels } from '@/api/chat'
import type { Channel } from '@/api/types'

export function ChatPage() {
  const { data: channels } = useChannels()
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const fromUrl = searchParams.get('channel')
    return fromUrl ? Number(fromUrl) : null
  })

  useEffect(() => {
    const fromUrl = searchParams.get('channel')
    if (fromUrl) setSelectedId(Number(fromUrl))
  }, [searchParams])

  const handleSelect = (channel: Channel) => {
    setSelectedId(channel.id)
    setSearchParams({}, { replace: true })
  }

  const selected = channels?.find((c) => c.id === selectedId) ?? channels?.[0] ?? null

  return (
    <div className={styles.layout}>
      <ChannelList selectedChannelId={selected?.id ?? null} onSelect={handleSelect} />
      {selected ? (
        <MessageThread channel={selected} />
      ) : (
        <div className={styles.thread}>
          <div className={styles.empty}>Select a channel to start chatting.</div>
        </div>
      )}
    </div>
  )
}
