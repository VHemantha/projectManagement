import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import type { ChatMessage } from './types'
import { useAuthStore } from '@/store/authStore'

type ConnectionState = 'connecting' | 'open' | 'closed'

interface TypingEvent {
  userId: number
  displayName: string
}

const MAX_BACKOFF_MS = 10_000

function wsUrl(channelId: number, token: string) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat/${channelId}/?token=${encodeURIComponent(token)}`
}

export function useChatSocket(channelId: number | undefined) {
  const queryClient = useQueryClient()
  const accessToken = useAuthStore((s) => s.accessToken)
  const [connectionState, setConnectionState] = useState<ConnectionState>('closed')
  const [typingUser, setTypingUser] = useState<TypingEvent | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const typingClearTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!channelId || !accessToken) return undefined
    // `cancelled` and `latestSocket` are local to THIS effect invocation (i.e. this one
    // channel subscription). Using a single shared ref for "was this close intentional"
    // across every channel switch is what caused the bug where a message sent in a
    // project/team channel would land in #general: switching channels tears down the old
    // socket and starts a new one, but the old socket's `onclose` can fire *after* the new
    // effect has already reset a shared flag — so the old handler "reconnects" to the OLD
    // channel and overwrites socketRef.current, silently redirecting sends there. Scoping
    // the cancellation state per-effect-run, and checking `socketRef.current === socket`
    // before a reconnect is allowed to touch the ref, makes stale sockets inert.
    let cancelled = false
    let latestSocket: WebSocket | null = null
    attemptRef.current = 0

    const connect = () => {
      if (cancelled) return
      setConnectionState('connecting')
      const socket = new WebSocket(wsUrl(channelId, accessToken))
      latestSocket = socket
      socketRef.current = socket

      socket.onopen = () => {
        attemptRef.current = 0
        setConnectionState('open')
      }

      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data)
        if (payload.type === 'message.new') {
          const message = payload.message as ChatMessage
          queryClient.setQueryData<ChatMessage[] | undefined>(
            ['chat', 'channels', channelId, 'messages'],
            (prev) => {
              if (!prev) return [message]
              // Drop this author's pending optimistic copy now that the real,
              // server-confirmed message has arrived over the broadcast.
              const withoutPending = prev.filter((m) => !(m._pending && m.author.id === message.author.id))
              if (withoutPending.some((m) => m.id === message.id)) return withoutPending
              return [...withoutPending, message]
            },
          )
          queryClient.invalidateQueries({ queryKey: ['chat', 'channels'] })
        } else if (payload.type === 'typing') {
          setTypingUser({ userId: payload.user_id, displayName: payload.display_name })
          if (typingClearTimer.current) clearTimeout(typingClearTimer.current)
          typingClearTimer.current = setTimeout(() => setTypingUser(null), 3000)
        }
      }

      socket.onclose = () => {
        // A stale socket from a superseded effect run (e.g. the user already switched
        // channels) must never resurrect itself into socketRef — only the socket that is
        // still the active one for THIS channel is allowed to trigger a reconnect.
        if (socketRef.current !== socket) return
        setConnectionState('closed')
        if (cancelled) return
        const delay = Math.min(1000 * 2 ** attemptRef.current, MAX_BACKOFF_MS)
        attemptRef.current += 1
        reconnectTimer.current = setTimeout(connect, delay)
      }

      socket.onerror = () => {
        socket.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (typingClearTimer.current) clearTimeout(typingClearTimer.current)
      latestSocket?.close()
    }
  }, [channelId, accessToken, queryClient])

  const sendMessage = useCallback(
    (body: Record<string, unknown>, parentMessageId?: number, mentionedUserIds?: number[]) => {
      if (!channelId || socketRef.current?.readyState !== WebSocket.OPEN) return

      const currentUser = useAuthStore.getState().user
      if (currentUser) {
        const optimistic: ChatMessage = {
          id: -Date.now(),
          channel: channelId,
          author: currentUser,
          body,
          created_at: new Date().toISOString(),
          edited_at: null,
          parent_message: parentMessageId ?? null,
          pinned: false,
          is_system: false,
          reactions: [],
          issue_links: [],
          mentions: [],
          reply_count: 0,
          attachments: [],
          _pending: true,
        }
        queryClient.setQueryData<ChatMessage[] | undefined>(
          ['chat', 'channels', channelId, 'messages'],
          (prev) => [...(prev ?? []), optimistic],
        )
      }

      socketRef.current.send(
        JSON.stringify({
          type: 'message.send',
          body,
          parent_message_id: parentMessageId,
          mentioned_user_ids: mentionedUserIds,
        }),
      )
    },
    [channelId, queryClient],
  )

  const sendTyping = useCallback(() => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'typing' }))
    }
  }, [])

  return { connectionState, sendMessage, sendTyping, typingUser }
}
