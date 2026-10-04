import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from './AppShell'
import { LegacyTeamsRedirect, LegacyWorkspacesRedirect, WorkspaceRoute } from './LegacyRedirects'
import { PlaceholderPage } from './PlaceholderPage'
import { ProtectedRoute } from './ProtectedRoute'
import { LoginPage } from '@/features/auth/LoginPage'
import { SignupPage } from '@/features/auth/SignupPage'
import { ProfilePage } from '@/features/profile/ProfilePage'
import { EpicBoardPage } from '@/features/board/EpicBoardPage'
import { MyWorkPage } from '@/features/board/MyWorkPage'
import { IssueDetailPage } from '@/features/issues/IssueDetailPage'
import { PeopleDirectoryPage } from '@/features/people/PeopleDirectoryPage'
import { UserWorkloadPage } from '@/features/people/UserWorkloadPage'
import { ProjectLayout, WorkspaceSectionRedirect } from '@/features/projects/ProjectLayout'
import { ProjectsListPage } from '@/features/projects/ProjectsListPage'
import { ProjectsSectionLayout } from '@/features/projects/ProjectsSectionLayout'
import { DashboardHomePage } from '@/features/dashboard/DashboardHomePage'
import { FiltersPage } from '@/features/search/FiltersPage'
import { AllIssuesBoardPage } from '@/features/board/AllIssuesBoardPage'
import { TeamsListPage } from '@/features/teams/TeamsListPage'
import { ChatPage } from '@/features/chat/ChatPage'
import { TimeReportsPage } from '@/features/timesheets/TimeReportsPage'
import { TimesheetApprovalInboxPage } from '@/features/timesheets/TimesheetApprovalInboxPage'
import { TimesheetGridPage } from '@/features/timesheets/TimesheetGridPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/', element: <MyWorkPage /> },
          // Workspace > Sub-workspace > Project > Task. Projects (and their tasks) live under
          // /projects; workspaces under /workspaces. See LegacyRedirects for the older URLs.
          { path: '/projects/:key/issues/:issueKey', element: <IssueDetailPage /> },
          { path: '/projects/:key/epics/:epicKey/board', element: <EpicBoardPage /> },
          {
            path: '/projects',
            element: <ProjectsSectionLayout />,
            children: [
              { index: true, element: <ProjectsListPage /> },
              // Hyphenated on purpose: project keys are letters/digits only, so this can never
              // shadow a real project's /projects/:key route.
              { path: 'all-issues', element: <AllIssuesBoardPage /> },
              // One page per project; its sections are tabs picked with ?tab=.
              { path: ':key', element: <ProjectLayout /> },
              // Old per-section URLs (/board, /issues, /settings …) open the matching tab.
              { path: ':key/:section', element: <WorkspaceSectionRedirect /> },
            ],
          },
          { path: '/workspaces', element: <TeamsListPage /> },
          // A number is a workspace; anything else is an old project link and is redirected.
          { path: '/workspaces/:teamId', element: <WorkspaceRoute /> },
          { path: '/workspaces/*', element: <LegacyWorkspacesRedirect /> },
          { path: '/teams/*', element: <LegacyTeamsRedirect /> },
          { path: '/people', element: <PeopleDirectoryPage /> },
          { path: '/people/:userId', element: <UserWorkloadPage /> },
          { path: '/filters', element: <FiltersPage /> },
          { path: '/dashboards', element: <DashboardHomePage /> },
          { path: '/chat', element: <ChatPage /> },
          { path: '/timesheets', element: <TimesheetGridPage /> },
          { path: '/timesheets/review', element: <TimesheetApprovalInboxPage /> },
          { path: '/timesheets/reports', element: <TimeReportsPage /> },
          { path: '/apps', element: <PlaceholderPage title="Apps" hint="Coming soon." /> },
          { path: '/profile', element: <ProfilePage /> },
        ],
      },
    ],
  },
])
