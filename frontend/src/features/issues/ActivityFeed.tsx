import type { JSONContent } from '@tiptap/react'
import { formatDistanceToNow } from 'date-fns'
import { MessageSquare } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './IssueView.module.css'
import { useAddComment, useComments, useIssueChatLinks, useIssueHistory } from '@/api/issues'
import { Avatar, Button, RichTextEditor, Tabs, TabsContent, TabsList, TabsTrigger, isDocEmpty } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

const FIELD_LABELS: Record<string, string> = {
  summary: 'summary',
  status: 'status',
  priority: 'priority',
  assignee: 'assignee',
  epic: 'epic',
  parent: 'parent',
  sprint: 'sprint',
  story_points: 'story points',
  due_date: 'due date',
}

function HistoryLine({ entry }: { entry: { user: { display_name: string } | null; field_changed: string; old_value: string; new_value: string } }) {
  const field = FIELD_LABELS[entry.field_changed] ?? entry.field_changed
  const from = entry.old_value || '—'
  const to = entry.new_value || '—'
  return (
    <div className={styles.historyText}>
      <b>{entry.user?.display_name ?? 'Someone'}</b> changed {field} from <b>{from}</b> to <b>{to}</b>
    </div>
  )
}

function CommentComposer({ issueKey }: { issueKey: string }) {
  const currentUser = useAuthStore((s) => s.user)
  const addComment = useAddComment(issueKey)
  const [draft, setDraft] = useState<JSONContent | null>(null)

  if (!currentUser) return null

  const handleSubmit = () => {
    if (!draft || isDocEmpty(draft)) return
    addComment.mutate(draft, { onSuccess: () => setDraft(null) })
  }

  return (
    <div className={styles.commentRow}>
      <Avatar name={currentUser.display_name} src={currentUser.avatar} size={32} />
      <div style={{ flex: 1 }}>
        <RichTextEditor
          key={addComment.isSuccess ? 'reset' : 'compose'}
          content={draft}
          onChange={setDraft}
          editable
          placeholder="Add a comment…"
        />
        <div className={styles.editActions}>
          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={addComment.isPending || !draft || isDocEmpty(draft)}
          >
            Comment
          </Button>
        </div>
      </div>
    </div>
  )
}

function ChatLinkRow({ link }: { link: { id: number; message_id: number; channel_id: number; channel_name: string; author: { display_name: string; avatar: string | null }; created_at: string; created_task: boolean } }) {
  return (
    <div className={styles.commentRow}>
      <Avatar name={link.author.display_name} src={link.author.avatar} size={32} />
      <div className={styles.commentBody}>
        <div className={styles.commentMeta}>
          <span className={styles.commentAuthor}>{link.author.display_name}</span>
          <span className={styles.commentTime}>
            {formatDistanceToNow(new Date(link.created_at), { addSuffix: true })}
          </span>
          <MessageSquare size={12} color="var(--tf-text-subtle)" />
          <span className={styles.commentTime}>
            {link.created_task ? 'created this issue from chat' : 'linked a chat message'}
          </span>
        </div>
        <div style={{ padding: '4px 12px 8px' }}>
          <Link to={`/chat?channel=${link.channel_id}`} style={{ fontSize: 12 }}>
            View in #{link.channel_name} →
          </Link>
        </div>
      </div>
    </div>
  )
}

export function ActivityFeed({ issueKey }: { issueKey: string }) {
  const { data: comments } = useComments(issueKey)
  const { data: history } = useIssueHistory(issueKey)
  const { data: chatLinks } = useIssueChatLinks(issueKey)

  const combined = [
    ...(comments ?? []).map((c) => ({ type: 'comment' as const, timestamp: c.created_at, data: c })),
    ...(history ?? []).map((h) => ({ type: 'history' as const, timestamp: h.timestamp, data: h })),
    ...(chatLinks ?? []).map((l) => ({ type: 'chat' as const, timestamp: l.created_at, data: l })),
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

  return (
    <Tabs defaultValue="comments">
      <TabsList>
        <TabsTrigger value="comments">Comments ({comments?.length ?? 0})</TabsTrigger>
        <TabsTrigger value="history">History</TabsTrigger>
        <TabsTrigger value="all">All</TabsTrigger>
      </TabsList>

      <TabsContent value="comments">
        <CommentComposer issueKey={issueKey} />
        {comments?.map((c) => (
          <div key={c.id} className={styles.commentRow}>
            <Avatar name={c.author.display_name} src={c.author.avatar} size={32} />
            <div className={styles.commentBody}>
              <div className={styles.commentMeta}>
                <span className={styles.commentAuthor}>{c.author.display_name}</span>
                <span className={styles.commentTime}>
                  {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                </span>
              </div>
              <RichTextEditor content={c.body} editable={false} showToolbar={false} />
            </div>
          </div>
        ))}
      </TabsContent>

      <TabsContent value="history">
        {history?.length ? (
          history.map((h) => (
            <div key={h.id} className={styles.historyRow}>
              <HistoryLine entry={h} />
              <span className={styles.commentTime} style={{ marginLeft: 'auto' }}>
                {formatDistanceToNow(new Date(h.timestamp), { addSuffix: true })}
              </span>
            </div>
          ))
        ) : (
          <div className={styles.metaText}>No changes yet.</div>
        )}
      </TabsContent>

      <TabsContent value="all">
        {combined.map((item) => {
          if (item.type === 'comment') {
            return (
              <div key={`c${item.data.id}`} className={styles.commentRow}>
                <Avatar name={item.data.author.display_name} src={item.data.author.avatar} size={32} />
                <div className={styles.commentBody}>
                  <div className={styles.commentMeta}>
                    <span className={styles.commentAuthor}>{item.data.author.display_name}</span>
                    <span className={styles.commentTime}>
                      {formatDistanceToNow(new Date(item.data.created_at), { addSuffix: true })}
                    </span>
                  </div>
                  <RichTextEditor content={item.data.body} editable={false} showToolbar={false} />
                </div>
              </div>
            )
          }
          if (item.type === 'chat') {
            return <ChatLinkRow key={`l${item.data.id}`} link={item.data} />
          }
          return (
            <div key={`h${item.data.id}`} className={styles.historyRow}>
              <HistoryLine entry={item.data} />
              <span className={styles.commentTime} style={{ marginLeft: 'auto' }}>
                {formatDistanceToNow(new Date(item.data.timestamp), { addSuffix: true })}
              </span>
            </div>
          )
        })}
      </TabsContent>
    </Tabs>
  )
}
