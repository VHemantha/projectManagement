import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import styles from './AppShell.module.css'
import { ErrorBoundary } from './ErrorBoundary'
import { GlobalSidebar } from './GlobalSidebar'
import { TopNav } from './TopNav'
import { useCurrentUser } from '@/api/auth'
import { CreateIssueModal } from '@/features/issues/CreateIssueModal'
import { IssueDetailModal } from '@/features/issues/IssueDetailModal'
import { QuickSearchModal } from '@/features/search/QuickSearchModal'

export function AppShell() {
  const [expanded, setExpanded] = useState(false)
  const location = useLocation()
  useCurrentUser()

  return (
    <div className={styles.shell}>
      <GlobalSidebar expanded={expanded} onToggle={() => setExpanded((v) => !v)} />
      <div className={styles.main}>
        <TopNav />
        <div className={styles.body}>
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </div>
      </div>
      <CreateIssueModal />
      <IssueDetailModal />
      <QuickSearchModal />
    </div>
  )
}
