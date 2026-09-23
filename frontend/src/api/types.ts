export interface User {
  id: number
  email: string
  username: string
  display_name: string
  job_title: string
  avatar: string | null
  is_staff: boolean
}

export type ProjectType = 'scrum' | 'kanban'

export interface ClientMini {
  id: number
  name: string
}

export interface TeamMini {
  id: number
  name: string
  avatar_color: string
}

export interface ProjectSummary {
  id: number
  key: string
  name: string
  description: string
  project_type: ProjectType
  lead: User | null
  avatar_color: string
  is_archived: boolean
  issue_count: number
  client: ClientMini | null
  primary_team: TeamMini | null
  created_at: string
  updated_at: string
}

export interface ProjectMembership {
  id: number
  user: User
  role: 'admin' | 'member' | 'viewer'
  joined_at: string
}

export interface Label {
  id: number
  name: string
  color: string
}

export interface Component {
  id: number
  name: string
  description: string
  lead: number | null
}

export interface Version {
  id: number
  name: string
  description: string
  release_date: string | null
  released: boolean
  archived: boolean
}

export interface ProjectDetail extends Omit<ProjectSummary, 'issue_count'> {
  default_assignee_rule: string
  memberships: ProjectMembership[]
  labels: Label[]
  components: Component[]
  versions: Version[]
  contributing_teams: TeamMini[]
  budgeted_hours: number | null
  job_value: string | null
  job_value_currency: string
}

export interface WorkflowStatus {
  id: number
  name: string
  category: 'todo' | 'in_progress' | 'done'
  order: number
}

export interface BoardColumn {
  name: string
  status_ids: number[]
  wip_limit: number | null
  /** Set only on synthetic columns built for cross-project boards (Team/My Work),
   * where a single status id can't represent every project's workflow. */
  category?: 'todo' | 'in_progress' | 'done'
}

export type CardFieldKey =
  | 'epic_tag'
  | 'story_points'
  | 'priority'
  | 'assignee'
  | 'labels'
  | 'due_date'
  | 'linked_issue_count'
  | 'time_logged'
  | 'current_responsible'

export type CardColorRule = 'none' | 'priority' | 'issue_type' | 'label'

export interface Board {
  id: number
  name: string
  board_type: ProjectType
  column_config: BoardColumn[]
  swimlane_mode: 'none' | 'epic' | 'assignee' | 'parent'
  card_fields: CardFieldKey[]
  card_color_rule: CardColorRule
  filters: number | null
  statuses: WorkflowStatus[]
}

export interface BoardConfig {
  id: number
  column_config: BoardColumn[]
  swimlane_mode: 'none' | 'epic' | 'assignee' | 'parent'
  card_fields: CardFieldKey[]
  card_color_rule: CardColorRule
  filters: number | null
}

export interface WorkflowTransitionItem {
  id: number
  name: string
  from_status: number | null
  from_status_name: string
  to_status: number
  to_status_name: string
  set_current_responsible_to: 'no_change' | 'preparer' | 'reviewer' | 'assignee'
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface TeamMembership {
  id: number
  user: User
  role: 'lead' | 'member'
  joined_at: string
}

export interface TeamSummary {
  id: number
  name: string
  description: string
  avatar_color: string
  member_count: number
  parent: TeamMini | null
  created_at: string
}

export interface TeamDetail {
  id: number
  name: string
  description: string
  avatar_color: string
  memberships: TeamMembership[]
  parent: TeamMini | null
  sub_teams: TeamMini[]
  created_at: string
}

export interface Sprint {
  id: number
  project_key: string
  name: string
  goal: string
  start_date: string | null
  end_date: string | null
  state: 'future' | 'active' | 'closed'
  order: number
  issue_count: number
  created_at: string
  completed_at: string | null
}

export interface IssueType {
  id: number
  name: string
  icon: string
  color: string
  is_subtask: boolean
  order: number
}

export type Priority = 'highest' | 'high' | 'medium' | 'low' | 'lowest'

export interface EpicMini {
  id: number
  key: string
  epic_name: string
  epic_color: string
}

export interface SprintMini {
  id: number
  name: string
  state: 'future' | 'active' | 'closed'
}

export interface IssueMini {
  id: number
  key: string
  summary: string
  issue_type: IssueType
  status: WorkflowStatus
  assignee: User | null
  priority: Priority
}

export interface IssueListItem {
  id: number
  key: string
  project_key: string
  summary: string
  issue_type: IssueType
  status: WorkflowStatus
  priority: Priority
  assignee: User | null
  reporter: User
  preparer: User | null
  reviewer: User | null
  current_responsible: User | null
  epic: EpicMini | null
  parent_id: number | null
  sprint: SprintMini | null
  story_points: number | null
  start_date: string | null
  due_date: string | null
  labels: Label[]
  rank: string
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export interface BurndownData {
  dates: string[]
  ideal: number[]
  remaining: (number | null)[]
  total_points: number
}

export interface VelocityRow {
  sprint: string
  committed: number
  completed: number
}

export interface IssueDetail {
  id: number
  key: string
  project: string
  summary: string
  description: Record<string, unknown> | null
  issue_type: IssueType
  status: WorkflowStatus
  priority: Priority
  assignee: User | null
  reporter: User
  preparer: User | null
  reviewer: User | null
  current_responsible: User | null
  epic: EpicMini | null
  epic_name: string
  epic_color: string
  parent: IssueMini | null
  sprint: SprintMini | null
  story_points: number | null
  budgeted_hours: number | null
  allocated_value: string | null
  original_estimate: string | null
  time_spent: string | null
  start_date: string | null
  due_date: string | null
  labels: Label[]
  components: { id: number; name: string }[]
  fix_versions: { id: number; name: string }[]
  subtasks: IssueMini[]
  watcher_count: number
  is_watching: boolean
  rank: string
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export type ChannelType = 'project' | 'team' | 'direct_message' | 'group_dm' | 'general' | 'topic'

export interface Channel {
  id: number
  name: string
  description: string
  channel_type: ChannelType
  linked_project: number | null
  project_key: string | null
  linked_team: number | null
  team_id: number | null
  is_private: boolean
  created_by: number | null
  created_at: string
  archived_at: string | null
  unread_count: number
  /** Populated only for direct_message/group_dm channels — see ChannelSerializer.participants
   * on the backend. Used to render a per-viewer "Jane Doe" label since a DM's stored `name`
   * isn't a meaningful display value (it's the same string shown to every participant). */
  participants: User[]
  has_messages: boolean
}

export interface ChannelMembership {
  id: number
  user: User
  role: 'owner' | 'member'
  muted: boolean
  last_read_at: string | null
  notification_preference: 'all' | 'mentions_only' | 'none'
  joined_at: string
}

export interface MessageReactionItem {
  id: number
  user: User
  emoji: string
}

export interface MessageIssueLinkItem {
  id: number
  issue: IssueMini
  created_task: boolean
  created_at: string
}

export interface MessageMentionItem {
  id: number
  mentioned_user: User
}

export interface ChatMessage {
  id: number
  channel: number
  author: User
  body: Record<string, unknown>
  created_at: string
  edited_at: string | null
  parent_message: number | null
  pinned: boolean
  is_system: boolean
  reactions: MessageReactionItem[]
  issue_links: MessageIssueLinkItem[]
  mentions: MessageMentionItem[]
  reply_count: number
  attachments: Attachment[]
  /** Client-only: set on the temporary optimistic copy shown before the server
   * broadcast confirms the send. Never present on a real API response. */
  _pending?: boolean
}

export interface TimeEntryTag {
  id: number
  name: string
  color: string
}

export type TimeEntryCreatedVia = 'timer' | 'manual' | 'chat_command'

export interface TimeEntry {
  id: number
  user: User
  issue: IssueMini | null
  project: number | null
  project_key: string | null
  description: string
  started_at: string | null
  ended_at: string | null
  duration_seconds: number
  is_billable: boolean
  is_running: boolean
  tags: TimeEntryTag[]
  created_via: TimeEntryCreatedVia
  locked: boolean
  work_date: string
  created_at: string
}

export type TimesheetStatus = 'draft' | 'submitted' | 'approved' | 'rejected'

export interface Timesheet {
  id: number
  user: User
  period_start: string
  period_end: string
  status: TimesheetStatus
  submitted_at: string | null
  reviewed_by: User | null
  reviewed_at: string | null
  reviewer_note: string
  total_hours: number
}

export interface IssueChatLink {
  id: number
  message_id: number
  channel_id: number
  channel_name: string
  author: User
  body: Record<string, unknown>
  created_at: string
  created_task: boolean
}

export interface SavedFilter {
  id: number
  name: string
  owner: number
  owner_name: string
  query: Record<string, unknown>
  is_public: boolean
  created_at: string
  updated_at: string
}

export interface NotificationItem {
  id: number
  actor: User | null
  verb: 'assigned' | 'mentioned' | 'commented' | 'status_changed' | 'watching_updated'
  target_issue_key: string | null
  target_issue_summary: string | null
  target_project_key: string | null
  target_channel_id: number | null
  target_channel_name: string | null
  is_read: boolean
  created_at: string
}

export interface Attachment {
  id: number
  file: string
  filename: string
  uploaded_by: User
  uploaded_at: string
}

export interface Comment {
  id: number
  author: User
  body: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface IssueHistoryEntry {
  id: number
  user: User | null
  field_changed: string
  old_value: string
  new_value: string
  timestamp: string
}

export interface RecentActivityEntry extends IssueHistoryEntry {
  issue_key: string
  issue_summary: string
  project_key: string
}

export type IssueLinkType = 'blocks' | 'is_blocked_by' | 'relates_to' | 'duplicates' | 'clones'

export interface IssueLink {
  id: number
  link_type: IssueLinkType
  target_issue: IssueMini
  created_at: string
}
