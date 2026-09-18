import type { JSONContent } from '@tiptap/react'
import { formatDistanceToNow } from 'date-fns'
import { ExternalLink, Paperclip, Plus, Trash2, X } from 'lucide-react'
import { type DragEvent, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import styles from './IssueView.module.css'
import { ActivityFeed } from './ActivityFeed'
import { IssueDetailsPanel } from './IssueDetailsPanel'
import {
  useAddIssueLink,
  useAddSubtask,
  useAttachments,
  useDeleteAttachment,
  useIssue,
  useIssueLinks,
  useIssues,
  useRemoveIssueLink,
  useUpdateIssue,
  useUploadAttachment,
} from '@/api/issues'
import type { IssueLinkType, IssueMini } from '@/api/types'
import { Button, IssueKey, IssueTypeIcon, PriorityIcon, RichTextEditor, Skeleton, StatusBadge, isDocEmpty } from '@/design-system'
import type { StatusCategory } from '@/design-system'
import { TimerButton } from '@/features/timesheets/TimerButton'
import { useUiStore } from '@/store/uiStore'

const LINK_TYPES: IssueLinkType[] = ['blocks', 'is_blocked_by', 'relates_to', 'duplicates', 'clones']

function SubtasksSection({ issueKey, subtasks }: { issueKey: string; subtasks: IssueMini[] }) {
  const addSubtask = useAddSubtask(issueKey)
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const [draft, setDraft] = useState('')

  const submit = () => {
    if (!draft.trim()) return
    addSubtask.mutate(draft.trim(), { onSuccess: () => setDraft('') })
  }

  return (
    <div>
      <div className={styles.sectionLabel}>Sub-tasks ({subtasks.length})</div>
      {subtasks.map((s) => (
        <div key={s.id} className={styles.subtaskRow} onClick={() => openIssueModal(s.key)}>
          <IssueTypeIcon typeName={s.issue_type.name} size={14} />
          <IssueKey value={s.key} />
          <span className={styles.subtaskSummary}>{s.summary}</span>
          <StatusBadge label={s.status.name} category={s.status.category as StatusCategory} />
        </div>
      ))}
      <div className={styles.addRow}>
        <input
          className={styles.panelSelect}
          style={{ flex: 1 }}
          placeholder="Add a sub-task…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
          }}
        />
        <Button variant="secondary" size="sm" onClick={submit} disabled={!draft.trim() || addSubtask.isPending}>
          <Plus size={14} /> Add
        </Button>
      </div>
    </div>
  )
}

function LinkedIssuesSection({ issueKey, projectKey }: { issueKey: string; projectKey: string }) {
  const { data: links } = useIssueLinks(issueKey)
  const addLink = useAddIssueLink(issueKey)
  const removeLink = useRemoveIssueLink(issueKey)
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const [adding, setAdding] = useState(false)
  const [linkType, setLinkType] = useState<IssueLinkType>('relates_to')
  const [search, setSearch] = useState('')
  const { data: results } = useIssues({ project: projectKey, search, page_size: 5 }, search.length >= 2)

  return (
    <div>
      <div className={styles.sectionLabel}>Linked issues ({links?.length ?? 0})</div>
      {links?.map((l) => (
        <div key={l.id} className={styles.linkRow}>
          <span className={styles.linkType}>{l.link_type.replace(/_/g, ' ')}</span>
          <IssueTypeIcon typeName={l.target_issue.issue_type.name} size={14} />
          <span className={styles.linkTarget} onClick={() => openIssueModal(l.target_issue.key)}>
            <IssueKey value={l.target_issue.key} /> {l.target_issue.summary}
          </span>
          <Button variant="subtle" size="sm" iconOnly onClick={() => removeLink.mutate(l.id)} aria-label="Remove link">
            <Trash2 size={13} />
          </Button>
        </div>
      ))}

      {adding ? (
        <div style={{ marginTop: 8 }}>
          <div className={styles.addRow}>
            <select
              className={styles.panelSelect}
              style={{ maxWidth: 160 }}
              value={linkType}
              onChange={(e) => setLinkType(e.target.value as IssueLinkType)}
            >
              {LINK_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            <input
              className={styles.panelSelect}
              style={{ flex: 1 }}
              placeholder="Search by key or summary…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoFocus
            />
            <Button variant="subtle" size="sm" iconOnly onClick={() => setAdding(false)} aria-label="Cancel">
              <X size={14} />
            </Button>
          </div>
          {results && results.results.length > 0 && (
            <div style={{ border: '1px solid var(--tf-border)', borderRadius: 4, marginTop: 4 }}>
              {results.results
                .filter((r) => r.key !== issueKey)
                .map((r) => (
                  <div
                    key={r.id}
                    className={styles.subtaskRow}
                    onClick={() => {
                      addLink.mutate({ target_issue_id: r.id, link_type: linkType })
                      setSearch('')
                      setAdding(false)
                    }}
                  >
                    <IssueTypeIcon typeName={r.issue_type.name} size={14} />
                    <IssueKey value={r.key} />
                    <span className={styles.subtaskSummary}>{r.summary}</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => setAdding(true)} style={{ marginTop: 8 }}>
          <Plus size={14} /> Link issue
        </Button>
      )}
    </div>
  )
}

function AttachmentsSection({ issueKey }: { issueKey: string }) {
  const { data: attachments } = useAttachments(issueKey)
  const upload = useUploadAttachment(issueKey)
  const remove = useDeleteAttachment(issueKey)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) upload.mutate(file)
  }

  return (
    <div>
      <div className={styles.sectionLabel}>Attachments ({attachments?.length ?? 0})</div>
      <div
        className={`${styles.dropzone} ${dragOver ? styles.dragOver : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <Paperclip size={16} style={{ marginBottom: 4 }} />
        <div>Drag and drop a file, or click to browse</div>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) upload.mutate(file)
            e.target.value = ''
          }}
        />
      </div>
      {attachments?.map((a) => (
        <div key={a.id} className={styles.attachmentRow}>
          <Paperclip size={13} />
          <a className={styles.attachmentName} href={a.file} target="_blank" rel="noreferrer">
            {a.filename}
          </a>
          <span className={styles.metaText}>{formatDistanceToNow(new Date(a.uploaded_at), { addSuffix: true })}</span>
          <Button variant="subtle" size="sm" iconOnly onClick={() => remove.mutate(a.id)} aria-label="Delete attachment">
            <Trash2 size={13} />
          </Button>
        </div>
      ))}
    </div>
  )
}

interface IssueViewProps {
  issueKey: string
  isModal?: boolean
  onClose?: () => void
}

export function IssueView({ issueKey, isModal, onClose }: IssueViewProps) {
  const { data: issue, isLoading } = useIssue(issueKey)
  const updateIssue = useUpdateIssue(issueKey)
  const [editingSummary, setEditingSummary] = useState(false)
  const [summaryDraft, setSummaryDraft] = useState('')
  const [editingDescription, setEditingDescription] = useState(false)
  const [descriptionDraft, setDescriptionDraft] = useState<JSONContent | null>(null)

  if (isLoading || !issue) {
    return (
      <div style={{ padding: isModal ? 0 : 32, maxWidth: 640 }}>
        <Skeleton width="70%" height={22} style={{ marginBottom: 20 }} />
        <Skeleton width={120} height={12} style={{ marginBottom: 12 }} />
        <Skeleton height={12} style={{ marginBottom: 8 }} />
        <Skeleton height={12} style={{ marginBottom: 8 }} />
        <Skeleton width="60%" height={12} />
      </div>
    )
  }

  const startEditSummary = () => {
    setSummaryDraft(issue.summary)
    setEditingSummary(true)
  }
  const saveSummary = () => {
    if (summaryDraft.trim() && summaryDraft !== issue.summary) {
      updateIssue.mutate({ summary: summaryDraft.trim() })
    }
    setEditingSummary(false)
  }

  const startEditDescription = () => {
    setDescriptionDraft(issue.description ?? null)
    setEditingDescription(true)
  }
  const saveDescription = () => {
    updateIssue.mutate({ description: descriptionDraft })
    setEditingDescription(false)
  }

  return (
    <div className={isModal ? undefined : styles.page}>
      <div className={styles.breadcrumb}>
        <Link to="/projects">Projects</Link> / <Link to={`/projects/${issue.project}`}>{issue.project}</Link> /{' '}
        <IssueKey value={issue.key} />
        {isModal && (
          <div className={styles.headerActions} style={{ marginLeft: 'auto' }}>
            <Link to={`/projects/${issue.project}/issues/${issue.key}`} onClick={onClose}>
              <Button variant="subtle" size="sm" iconOnly aria-label="Open full page">
                <ExternalLink size={14} />
              </Button>
            </Link>
            {onClose && (
              <Button variant="subtle" size="sm" iconOnly onClick={onClose} aria-label="Close">
                <X size={14} />
              </Button>
            )}
          </div>
        )}
      </div>

      <div className={styles.headerRow}>
        <div className={styles.typeKeyRow}>
          <IssueTypeIcon typeName={issue.issue_type.name} size={16} />
          <IssueKey value={issue.key} />
          <StatusBadge label={issue.status.name} category={issue.status.category as StatusCategory} />
          <PriorityIcon priority={issue.priority} />
          <TimerButton issueId={issue.id} iconOnly={false} size="sm" />
        </div>
        {issue.issue_type.name === 'Epic' && (
          <Link to={`/projects/${issue.project}/epics/${issue.key}/board`} onClick={onClose}>
            <Button variant="secondary" size="sm">
              View epic on board
            </Button>
          </Link>
        )}
      </div>

      <div className={styles.layout}>
        <div>
          {editingSummary ? (
            <input
              className={styles.summaryInput}
              autoFocus
              value={summaryDraft}
              onChange={(e) => setSummaryDraft(e.target.value)}
              onBlur={saveSummary}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveSummary()
                if (e.key === 'Escape') setEditingSummary(false)
              }}
            />
          ) : (
            <div className={styles.summary} onClick={startEditSummary}>
              {issue.summary}
            </div>
          )}

          <div className={styles.sectionLabel}>Description</div>
          {editingDescription ? (
            <div>
              <RichTextEditor content={descriptionDraft} onChange={setDescriptionDraft} editable autofocus />
              <div className={styles.editActions}>
                <Button variant="primary" size="sm" onClick={saveDescription}>
                  Save
                </Button>
                <Button variant="subtle" size="sm" onClick={() => setEditingDescription(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : isDocEmpty(issue.description) ? (
            <div className={styles.descriptionDisplay} onClick={startEditDescription}>
              <div className={styles.descriptionPlaceholder}>Add a description…</div>
            </div>
          ) : (
            <div className={styles.descriptionDisplay} onClick={startEditDescription}>
              <RichTextEditor content={issue.description} editable={false} showToolbar={false} />
            </div>
          )}

          <SubtasksSection issueKey={issue.key} subtasks={issue.subtasks} />

          <div style={{ marginTop: 20 }}>
            <LinkedIssuesSection issueKey={issue.key} projectKey={issue.project} />
          </div>

          <div style={{ marginTop: 20 }}>
            <AttachmentsSection issueKey={issue.key} />
          </div>

          <div className={styles.sectionLabel}>Activity</div>
          <ActivityFeed issueKey={issue.key} />
        </div>

        <IssueDetailsPanel issue={issue} />
      </div>
    </div>
  )
}
