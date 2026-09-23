import { createBrowserRouter } from 'react-router-dom'

import { AppShell } from './AppShell'
import { PlaceholderPage } from './PlaceholderPage'
import { ProtectedRoute } from './ProtectedRoute'
import { LoginPage } from '@/features/auth/LoginPage'
import { SignupPage } from '@/features/auth/SignupPage'
import { ProfilePage } from '@/features/profile/ProfilePage'
import { BacklogPage } from '@/features/backlog/BacklogPage'
import { EpicBoardPage } from '@/features/board/EpicBoardPage'
import { MyWorkPage } from '@/features/board/MyWorkPage'
import { ProjectBoardPage } from '@/features/board/ProjectBoardPage'
import { IssueDetailPage } from '@/features/issues/IssueDetailPage'
import { PeopleDirectoryPage } from '@/features/people/PeopleDirectoryPage'
import { UserWorkloadPage } from '@/features/people/UserWorkloadPage'
import { ProjectIssuesPage } from '@/features/projects/ProjectIssuesPage'
import { ProjectLayout } from '@/features/projects/ProjectLayout'
import { ProjectSettingsPage } from '@/features/projects/ProjectSettingsPage'
import { ProjectSummaryPage } from '@/features/projects/ProjectSummaryPage'
import { ProjectsListPage } from '@/features/projects/ProjectsListPage'
import { ProjectsSectionLayout } from '@/features/projects/ProjectsSectionLayout'
import { DashboardHomePage } from '@/features/dashboard/DashboardHomePage'
import { SprintReportPage } from '@/features/reports/SprintReportPage'
import { FiltersPage } from '@/features/search/FiltersPage'
import { TimelinePage } from '@/features/timeline/TimelinePage'
import { TeamDetailPage } from '@/features/teams/TeamDetailPage'
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
          { path: '/projects/:key/issues/:issueKey', element: <IssueDetailPage /> },
          { path: '/projects/:key/epics/:epicKey/board', element: <EpicBoardPage /> },
          {
            path: '/projects',
            element: <ProjectsSectionLayout />,
            children: [
              { index: true, element: <ProjectsListPage /> },
              {
                path: ':key',
                element: <ProjectLayout />,
                children: [
                  { index: true, element: <ProjectSummaryPage /> },
                  { path: 'board', element: <ProjectBoardPage /> },
                  { path: 'backlog', element: <BacklogPage /> },
                  { path: 'timeline', element: <TimelinePage /> },
                  { path: 'issues', element: <ProjectIssuesPage /> },
                  { path: 'reports', element: <SprintReportPage /> },
                  { path: 'settings', element: <ProjectSettingsPage /> },
                ],
              },
            ],
          },
          { path: '/teams', element: <TeamsListPage /> },
          { path: '/teams/:teamId', element: <TeamDetailPage /> },
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
