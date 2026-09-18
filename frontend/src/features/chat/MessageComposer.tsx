import type { JSONContent } from '@tiptap/react'
import { AtSign, Paperclip, Send, X } from 'lucide-react'
import { useRef, useState } from 'react'

import styles from './ChatPage.module.css'
import { extractPlainText } from './richTextPlainText'
import { useChannelMembers, useSendMessageWithAttachment } from '@/api/chat'
import type { Channel, User } from '@/api/types'
import {
  Avatar,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  RichTextEditor,
  isDocEmpty,
} from '@/design-system'
import { useUiStore } from '@/store/uiStore'

interface MessageComposerProps {
  channel: Channel
  onSend: (body: Record<string, unknown>, mentionedUserIds: number[]) => void
  onTyping?: () => void
}

export function MessageComposer({ channel, onSend, onTyping }: MessageComposerProps) {
  const [draft, setDraft] = useState<JSONContent | null>(null)
  const [mentioned, setMentioned] = useState<User[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [resetKey, setResetKey] = useState(0)
  const { data: members } = useChannelMembers(channel.id)
  const openCreateIssue = useUiStore((s) => s.openCreateIssue)
  const sendWithAttachment = useSendMessageWithAttachment(channel.id)
  const lastTypingSentAt = useRef(0)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleChange = (json: JSONContent) => {
    setDraft(json)
    const now = Date.now()
    if (onTyping && now - lastTypingSentAt.current > 2000) {
      lastTypingSentAt.current = now
      onTyping()
    }
  }

  const plainText = extractPlainText(draft as Record<string, unknown> | null | undefined, 4000)
  const isTaskCommand = plainText.trim().startsWith('/task ')
  const isTimerCommand = /^\/timer\s+\S+/.test(plainText.trim())

  const reset = () => {
    setDraft(null)
    setMentioned([])
    setFile(null)
    setResetKey((k) => k + 1)
  }

  const handleSend = () => {
    if (!draft || isDocEmpty(draft)) return

    if (isTaskCommand) {
      openCreateIssue(channel.project_key)
      reset()
      return
    }
    if (isTimerCommand) {
      // Wired up to the real start-timer endpoint once the Timesheets timer
      // milestone lands; for now this just sends the command as a regular
      // message so nothing is silently dropped.
    }

    if (file) {
      sendWithAttachment.mutate({ body: draft as Record<string, unknown>, file })
    } else {
      onSend(draft as Record<string, unknown>, mentioned.map((u) => u.id))
    }
    reset()
  }

  return (
    <div className={styles.composerWrap}>
      {mentioned.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
          {mentioned.map((u) => (
            <span
              key={u.id}
              style={{
                fontSize: 12,
                background: 'var(--tf-blue-subtle)',
                color: 'var(--tf-blue)',
                borderRadius: 999,
                padding: '2px 8px',
                cursor: 'pointer',
              }}
              onClick={() => setMentioned((prev) => prev.filter((m) => m.id !== u.id))}
            >
              @{u.display_name} ×
            </span>
          ))}
        </div>
      )}
      {file && (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
            background: 'var(--tf-surface-hover)',
            borderRadius: 6,
            padding: '3px 8px',
            marginBottom: 6,
          }}
        >
          <Paperclip size={12} /> {file.name}
          <X size={12} style={{ cursor: 'pointer' }} onClick={() => setFile(null)} />
        </div>
      )}
      <RichTextEditor
        key={resetKey}
        content={draft}
        onChange={handleChange}
        editable
        placeholder={`Message #${channel.name}… (try /task or /timer TRK-1)`}
      />
      <div className={styles.composerActions}>
        <Button
          variant="subtle"
          size="sm"
          iconOnly
          aria-label="Attach a file"
          onClick={() => fileInputRef.current?.click()}
        >
          <Paperclip size={14} />
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="subtle" size="sm" iconOnly aria-label="Mention someone">
              <AtSign size={14} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {members?.map((u) => (
              <DropdownMenuItem
                key={u.id}
                onSelect={() => setMentioned((prev) => (prev.some((m) => m.id === u.id) ? prev : [...prev, u]))}
              >
                <Avatar name={u.display_name} src={u.avatar} size={20} /> {u.display_name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <Button variant="primary" size="sm" onClick={handleSend} disabled={!draft || isDocEmpty(draft)}>
          <Send size={13} /> {isTaskCommand ? 'Open Create Issue' : 'Send'}
        </Button>
      </div>
    </div>
  )
}
