import { Navigate, useLocation, useParams, useSearchParams } from 'react-router-dom'

import styles from './ProjectLayout.module.css'
import { ProjectIssuesPage } from './ProjectIssuesPage'
import { ProjectSettingsPage } from './ProjectSettingsPage'
import { ProjectSummaryPage } from './ProjectSummaryPage'
import { WorkspaceContext } from './useProjectContext'
import { WorkspaceDashboardPanel } from './WorkspaceDashboardPanel'
import { isScrumWorkspace, resolveTab, tabForLegacySection, type WorkspaceTab, workspaceTabs } from './workspaceTabs'
import { useProject, useUpdateProject } from '@/api/projects'
import { PlaceholderPage } from '@/app/PlaceholderPage'
import { InlineEdit, Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'
import { BacklogPage } from '@/features/backlog/BacklogPage'
import { ProjectBoardPage } from '@/features/board/ProjectBoardPage'
import { SprintReportPage } from '@/features/reports/SprintReportPage'
import { TimelinePage } from '@/features/timeline/TimelinePage'

const TAB_PAGES: Record<WorkspaceTab, () => React.ReactElement> = {
  kanban: () => <ProjectBoardPage />,
  summary: () => <ProjectSummaryPage />,
  backlog: () => <BacklogPage />,
  tasks: () => <ProjectIssuesPage />,
  timeline: () => <TimelinePage />,
  reports: () => <SprintReportPage />,
  settings: () => <ProjectSettingsPage />,
}

/** A project: one page with a tab per section (?tab=kanban, ?tab=tasks, …), Kanban first. */
export function ProjectLayout() {
  const { key } = useParams<{ key: string }>()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const { data: project, isLoading } = useProject(key)
  const updateProject = useUpdateProject(project?.key ?? key ?? '')

  if (isLoading) return <PlaceholderPage title="Loading project…" />
  if (!project) return <PlaceholderPage title="Project not found" />
  // Opened by an old key (the project was renamed) or in different letter case.
  if (key !== project.key) {
    return <Navigate replace to={`/projects/${project.key}${location.search}`} />
  }

  const tabs = workspaceTabs(project)
  const tab = resolveTab(searchParams.get('tab'), project)
  // A hidden or unknown tab (e.g. ?tab=summary with the Summary feature off) lands on Kanban.
  const requested = searchParams.get('tab')
  if (requested && requested !== tab) {
    const params = new URLSearchParams(searchParams)
    params.set('tab', tab)
    return <Navigate replace to={`/projects/${project.key}?${params}`} />
  }
  const kind = project.is_client_workspace
    ? 'Tasks without a project'
    : isScrumWorkspace(project)
      ? 'Scrum project'
      : 'Project'
  // Where the project sits: Workspace › Sub-workspace.
  const placement = [project.primary_team?.name, project.client?.name].filter(Boolean).join(' › ')
  const subtitle = placement ? `${kind} in ${placement}` : kind

  return (
    <WorkspaceContext.Provider value={{ project }}>
      <div className={styles.layout}>
        <Tabs
          value={tab}
          // Each tab is its own history entry, so Back returns to the previous tab. Manual activation
          // (click/Enter/Space) so focusing a tab doesn't add a second entry.
          activationMode="manual"
          onValueChange={(next) => setSearchParams({ tab: next })}
          className={styles.tabs}
        >
          <header className={styles.header}>
            <span className={styles.projectAvatar} style={{ background: project.avatar_color }} aria-hidden="true">
              {project.key.slice(0, 2).toUpperCase()}
            </span>
            <div className={styles.headerText}>
              <InlineEdit
                as="h1"
                className={styles.projectName}
                value={project.name}
                label="Project name"
                canEdit={project.can_manage}
                onSave={(name) => updateProject.mutateAsync({ name })}
              />
              <div className={styles.projectType}>
                {project.key} · {subtitle}
              </div>
            </div>
            <div className={styles.tabBar}>
              <TabsList aria-label={`${project.name} sections`}>
                {tabs.map(({ id, label, icon: Icon }) => (
                  <TabsTrigger key={id} value={id}>
                    <Icon size={15} strokeWidth={1.9} aria-hidden="true" />
                    {label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
          </header>
          {/* Only the open tab is mounted, so hidden tabs fetch nothing. */}
          <TabsContent value={tab} className={styles.content}>
            {tab === 'kanban' ? (
              // The board shares its tab with the project dashboard panel on its right.
              <div className={styles.withPanel}>
                <div className={styles.main}>{TAB_PAGES.kanban()}</div>
                <WorkspaceDashboardPanel project={project} />
              </div>
            ) : (
              TAB_PAGES[tab]()
            )}
          </TabsContent>
        </Tabs>
      </div>
    </WorkspaceContext.Provider>
  )
}

/** Old sub-page URLs (/projects/KEY/board, /issues, /settings …) open the matching tab,
 * keeping any other query parameters. */
export function WorkspaceSectionRedirect() {
  const { key, section } = useParams<{ key: string; section: string }>()
  const location = useLocation()
  const params = new URLSearchParams(location.search)
  params.set('tab', tabForLegacySection(section))
  return <Navigate replace to={`/projects/${key}?${params}${location.hash}`} />
}
