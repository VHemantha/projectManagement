import type { JSONContent } from '@tiptap/react'
import { format, formatDistanceToNow, isAfter, parseISO } from 'date-fns'
import {
  Activity,
  Archive,
  ArchiveRestore,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  FolderOpen,
  Home,
  Layers,
  Paperclip,
  Plus,
  Trash2,
  X,
} from 'lucide-react'
import { type DragEvent, type ReactNode, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import styles from './IssueView.module.css'
import { ActivityFeed } from './ActivityFeed'
import { IssueDetailsPanel } from './IssueDetailsPanel'
import { StageBar } from './StageBar'
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
import { useJobPrecheck } from '@/api/precheck'
import { useProject, useProjectBoard } from '@/api/projects'
import type { IssueDetail, IssueLinkType, IssueMini } from '@/api/types'
import {
  Button,
  IssueKey,
  IssueTypeIcon,
  RichTextEditor,
  Skeleton,
  StatusBadge,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  isDocEmpty,
} from '@/design-system'
import type { StatusCategory } from '@/design-system'
import { DeleteTaskDialog } from '@/features/board/DeleteTaskDialog'
import { AIAssistant } from '@/features/precheck/AIAssistant'
import { Milestones } from '@/features/precheck/Milestones'
import { WpAgentPanel } from '@/features/precheck/WpAgentPanel'
import { TimerButton } from '@/features/timesheets/TimerButton'
import { sentenceCase } from '@/lib/text'
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
      <h2 className={styles.sectionTitle}>Sub-tasks ({subtasks.length})</h2>
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
      <h2 className={styles.sectionTitle}>Linked tasks ({links?.length ?? 0})</h2>
      {links?.map((l) => (
        <div key={l.id} className={styles.linkRow}>
          <span className={styles.linkType}>{sentenceCase(l.link_type)}</span>
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
            <div className={styles.searchResults}>
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
          <Plus size={14} /> Link task
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
      <h2 className={styles.sectionTitle}>Attachments ({attachments?.length ?? 0})</h2>
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

/** The task's Drive folder (set on the pre-check), where the AI reads its documents. */
function DriveFolder({ url }: { url: string | undefined }) {
  return (
    <div className={styles.driveFolder}>
      <FolderOpen size={18} aria-hidden="true" />
      {url ? (
        <a href={url} target="_blank" rel="noreferrer">
          Open the task's Google Drive folder <ExternalLink size={12} aria-hidden="true" />
        </a>
      ) : (
        <span className={styles.metaText}>No Drive folder yet. Add it in the pre-check (Overview, AI workspace).</span>
      )}
    </div>
  )
}

/** "Year ended 31 March 2026" from the financial year the accountant confirmed on the pre-check. */
function yearLabel(yearEnd: string | undefined): string {
  if (!yearEnd) return ''
  try {
    const end = parseISO(yearEnd)
    return `${isAfter(end, new Date()) ? 'Year ending' : 'Year ended'} ${format(end, 'd MMMM yyyy')}`
  } catch {
    return ''
  }
}

function Header({ issue, isModal, onClose, leave, summary }: {
  issue: IssueDetail
  isModal?: boolean
  onClose?: () => void
  leave?: () => void
  summary: ReactNode
}) {
  const updateIssue = useUpdateIssue(issue.key)
  const { data: project } = useProject(issue.project)
  const { data: board } = useProjectBoard(issue.project)
  const precheck = useJobPrecheck(issue.key).data
  const client = project?.client?.name
  const subtitle = [client ?? issue.project_name, yearLabel(precheck?.setup.settings?.year_end)].filter(Boolean)
  const [deleting, setDeleting] = useState(false)
  const navigate = useNavigate()
  // Gone: a window closes; a full page goes back to the project's board.
  const afterDelete = () => (onClose ? onClose() : navigate(`/projects/${issue.project}`, { replace: true }))

  return (
    <header className={styles.header}>
      <div className={styles.breadcrumb}>
        <nav aria-label="Breadcrumb" className={styles.crumbs}>
          <Link to="/" aria-label="Home" onClick={leave}>
            <Home size={16} />
          </Link>
          {project?.primary_team && (
            <>
              <span aria-hidden="true">/</span>
              <Link to={`/workspaces/${project.primary_team.id}`} onClick={leave}>
                {project.primary_team.name}
              </Link>
            </>
          )}
          <span aria-hidden="true">/</span>
          <Link to={`/projects/${issue.project}`} onClick={leave}>
            {issue.project_name}
          </Link>
          <span aria-hidden="true">/</span>
          <IssueKey value={issue.key} />
        </nav>
        <div className={styles.headerActions}>
          <TimerButton issueId={issue.id} iconOnly={false} size="sm" />
          <Button
            variant="subtle"
            size="sm"
            onClick={() => updateIssue.mutate({ is_archived: !issue.is_archived })}
            title={issue.is_archived ? 'Show this task on boards again' : 'Hide this task from boards and lists'}
          >
            {issue.is_archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
            {issue.is_archived ? 'Restore' : 'Archive'}
          </Button>
          {issue.can_delete && (
            <Button variant="subtle" size="sm" onClick={() => setDeleting(true)} title="Delete this task permanently" style={{ color: 'var(--tf-danger)' }}>
              <Trash2 size={14} /> Delete
            </Button>
          )}
          {isModal && (
            <Link to={`/projects/${issue.project}/issues/${issue.key}`} onClick={leave}>
              <Button variant="subtle" size="sm" iconOnly aria-label="Open full page">
                <ExternalLink size={14} />
              </Button>
            </Link>
          )}
          {onClose && (
            <Button variant="subtle" size="sm" iconOnly onClick={onClose} aria-label="Close">
              <X size={18} />
            </Button>
          )}
        </div>
      </div>

      <div className={styles.titleRow}>
        <span className={styles.titleIcon} aria-hidden="true">
          <FileText size={24} />
        </span>
        <div className={styles.titleText}>
          {summary}
          <p className={styles.subtitle}>
            {subtitle.map((part, i) => (
              <span key={part}>
                {i > 0 && <span aria-hidden="true"> • </span>}
                {part}
              </span>
            ))}
          </p>
        </div>
        <label className={styles.statusPill}>
          <Clock size={18} aria-hidden="true" />
          <span className={styles.srOnly}>Stage</span>
          <select value={issue.status.id} onChange={(e) => updateIssue.mutate({ status_id: Number(e.target.value) })}>
            {(board?.statuses ?? [issue.status]).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {issue.issue_type.name === 'Epic' && (
        <Link to={`/projects/${issue.project}/epics/${issue.key}/board`} onClick={leave}>
          <Button variant="secondary" size="sm">
            View epic on board
          </Button>
        </Link>
      )}
      {issue.can_delete && <DeleteTaskDialog issue={issue} open={deleting} onOpenChange={setDeleting} onDeleted={afterDelete} />}
    </header>
  )
}

interface IssueViewProps {
  issueKey: string
  isModal?: boolean
  onClose?: () => void
}

/** A task (AFIT, 12 Nov 2026 design): its header, then four tabs — Overview (description, the AI
 * workspace, Ask and the milestone bar with each stage's history), Documents, Workpapers and
 * Activity — beside its Job details and Time budget. Fields save as they change; in a window,
 * "Save changes" saves a description or title still being edited and closes. */
export function IssueView({ issueKey, isModal, onClose }: IssueViewProps) {
  const { data: issue, isLoading } = useIssue(issueKey)
  const updateIssue = useUpdateIssue(issueKey)
  // Opening a full page leaves every task window, not just this one.
  const closeAllIssueModals = useUiStore((s) => s.closeAllIssueModals)
  const leave = onClose ? closeAllIssueModals : undefined
  const precheck = useJobPrecheck(issueKey).data
  const [tab, setTab] = useState('overview')
  const [editingSummary, setEditingSummary] = useState(false)
  const [summaryDraft, setSummaryDraft] = useState('')
  const [editingDescription, setEditingDescription] = useState(false)
  const [descriptionDraft, setDescriptionDraft] = useState<JSONContent | null>(null)

  if (isLoading || !issue) {
    return (
      <div className={isModal ? styles.modalBody : styles.page}>
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
  const saveAndClose = () => {
    if (editingSummary) saveSummary()
    if (editingDescription) saveDescription()
    onClose?.()
  }

  const summary = editingSummary ? (
    <input
      className={styles.summaryInput}
      aria-label="Task name"
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
    <h1 className={styles.summary} onClick={startEditSummary} title="Click to rename">
      {issue.summary}
    </h1>
  )

  return (
    <div className={isModal ? styles.modal : styles.page}>
      <div className={isModal ? styles.modalBody : undefined}>
        <Header issue={issue} isModal={isModal} onClose={onClose} leave={leave} summary={summary} />

        {issue.is_archived && (
          <div className={styles.archivedBanner} role="status">
            <Archive size={14} />
            <span>
              {`This task is archived${
                issue.archived_at ? ` (${formatDistanceToNow(new Date(issue.archived_at), { addSuffix: true })})` : ''
              }. It's hidden from boards, the backlog and task lists.`}
            </span>
            <button type="button" onClick={() => updateIssue.mutate({ is_archived: false })}>
              Restore
            </button>
          </div>
        )}

        <Tabs value={tab} onValueChange={setTab}>
          <div className={styles.tabs}>
            <TabsList aria-label="Task sections">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="documents">
                <FileText size={16} aria-hidden="true" /> Documents
              </TabsTrigger>
              <TabsTrigger value="workpapers">
                <Layers size={16} aria-hidden="true" /> Workpapers
              </TabsTrigger>
              <TabsTrigger value="activity">
                <Activity size={16} aria-hidden="true" /> Activity
              </TabsTrigger>
            </TabsList>
          </div>

          <div className={styles.layout}>
            <div className={styles.main}>
              <TabsContent value="overview">
                <h2 className={styles.sectionTitle}>Description</h2>
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
                  <button type="button" className={styles.descriptionEmpty} onClick={startEditDescription}>
                    Add a description…
                  </button>
                ) : (
                  <div className={styles.descriptionDisplay} onClick={startEditDescription}>
                    <RichTextEditor content={issue.description} editable={false} showToolbar={false} />
                  </div>
                )}

                {/* The pre-check starts from the task and nowhere else. */}
                <AIAssistant jobKey={issue.key} />
                <StageBar issueKey={issue.key} />

                <div className={styles.block}>
                  <SubtasksSection issueKey={issue.key} subtasks={issue.subtasks} />
                </div>
                <div className={styles.block}>
                  <LinkedIssuesSection issueKey={issue.key} projectKey={issue.project} />
                </div>
              </TabsContent>

              <TabsContent value="documents">
                <h2 className={styles.sectionTitle}>Drive folder</h2>
                <DriveFolder url={precheck?.setup.drive_folder_url} />
                <div className={styles.block}>
                  <AttachmentsSection issueKey={issue.key} />
                </div>
              </TabsContent>

              <TabsContent value="workpapers">
                {/* Mounted only when open: the WP Agent loads its runs and form then. */}
                {tab === 'workpapers' && <WpAgentPanel jobKey={issue.key} />}
              </TabsContent>

              <TabsContent value="activity">
                <ActivityFeed issueKey={issue.key} />
                <div className={styles.block}>
                  <Milestones jobKey={issue.key} />
                </div>
              </TabsContent>
            </div>

            <IssueDetailsPanel issue={issue} />
          </div>
        </Tabs>
      </div>

      <footer className={styles.footer}>
        <span className={styles.updated}>
          <CheckCircle2 size={16} aria-hidden="true" />
          Last updated {formatDistanceToNow(new Date(issue.updated_at), { addSuffix: true })}
        </span>
        {onClose && (
          <div className={styles.footerActions}>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            <Button variant="primary" onClick={saveAndClose}>
              Save changes
            </Button>
          </div>
        )}
      </footer>
    </div>
  )
}
