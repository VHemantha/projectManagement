import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import styles from './AppShell.module.css'
import { Breadcrumbs } from './Breadcrumbs'
import { ErrorBoundary } from './ErrorBoundary'
import { GlobalSidebar } from './GlobalSidebar'
import { TopNav } from './TopNav'
import { useCurrentUser } from '@/api/auth'
import { usePresenceSocket } from '@/api/usePresenceSocket'
import { CreateIssueModal } from '@/features/issues/CreateIssueModal'
import { IssueDetailModal } from '@/features/issues/IssueDetailModal'
import { QuickSearchModal } from '@/features/search/QuickSearchModal'

export function AppShell() {
  // Desktop rail collapsed/expanded state.
  const [expanded, setExpanded] = useState(false)
  // Mobile slide-out drawer open/closed state (only relevant on small screens).
  const [drawerOpen, setDrawerOpen] = useState(false)
  const location = useLocation()
  useCurrentUser()
  usePresenceSocket()

  // Note: the drawer is closed explicitly by tapping a nav item or the backdrop.
  // While it's open it covers the whole screen, so no other navigation is
  // reachable — no route-change listener is needed.

  return (
    <div className={styles.shell}>
      <GlobalSidebar
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
        drawerOpen={drawerOpen}
        onCloseDrawer={() => setDrawerOpen(false)}
      />
      {/* Dimmed backdrop behind the mobile drawer; tapping it closes the drawer.
          Hidden on larger screens via CSS. */}
      {drawerOpen && <div className={styles.backdrop} onClick={() => setDrawerOpen(false)} />}
      <div className={styles.main}>
        <TopNav onOpenDrawer={() => setDrawerOpen(true)} />
        {/* Global, route-driven breadcrumb trail shown on every page. */}
        <Breadcrumbs />
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
