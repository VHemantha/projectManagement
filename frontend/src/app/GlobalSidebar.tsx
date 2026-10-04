import {
  ChevronsLeft,
  ChevronsRight,
  Clock,
  Contact,
  Grid3x3,
  LayoutDashboard,
  LayoutGrid,
  ListFilter,
  MessageSquare,
  Users,
  UserRound,
} from 'lucide-react'
import { Link, NavLink } from 'react-router-dom'

import styles from './AppShell.module.css'
import { ProjectSwitcher } from './ProjectSwitcher'
import { Tooltip } from '@/design-system'

// Each section has its own accent colour (see .navIcon in AppShell.module.css).
const NAV_ITEMS = [
  { to: '/', label: 'Your work', icon: UserRound, tone: 'violet', end: true },
  // The hierarchy, top down: Workspaces hold sub-workspaces, which hold projects.
  { to: '/workspaces', label: 'Workspaces', icon: Users, tone: 'teal' },
  { to: '/projects', label: 'Projects', icon: LayoutGrid, tone: 'blue' },
  { to: '/people', label: 'People', icon: Contact, tone: 'pink' },
  { to: '/filters', label: 'Filters', icon: ListFilter, tone: 'orange' },
  { to: '/dashboards', label: 'Dashboards', icon: LayoutDashboard, tone: 'green' },
  { to: '/chat', label: 'Chat', icon: MessageSquare, tone: 'violet' },
  { to: '/timesheets', label: 'Timesheets', icon: Clock, tone: 'orange' },
  { to: '/apps', label: 'Apps', icon: Grid3x3, tone: 'teal' },
]

interface GlobalSidebarProps {
  /** Desktop rail expanded (wide, labels visible). */
  expanded: boolean
  onToggle: () => void
  /** Mobile drawer visible (slides the rail in over the page). */
  drawerOpen: boolean
  onCloseDrawer: () => void
}

export function GlobalSidebar({ expanded, onToggle, drawerOpen, onCloseDrawer }: GlobalSidebarProps) {
  // Labels are shown whenever the rail is wide: on desktop when expanded, and on
  // mobile whenever the drawer is open (a drawer is always the full-width rail).
  const showLabels = expanded || drawerOpen

  return (
    <aside
      className={`${styles.sidebar} ${showLabels ? styles.expanded : ''} ${
        drawerOpen ? styles.drawerOpen : ''
      }`}
    >
      {/* The logo doubles as a home button: clicking it takes the user back to
          the "Your work" landing page (/), the way the Jira/Atlassian logo does. */}
      <Tooltip label="Home" side="right">
        <Link to="/" className={styles.sidebarHeader} aria-label="Go to home">
          {/* TrackFlow brand mark (the same SVG used as the browser favicon). */}
          <span className={styles.sidebarLogoMark}>
            <img src="/favicon.svg" alt="" width={28} height={28} />
          </span>
          {showLabels && <span className={styles.sidebarLogoText}>TrackFlow</span>}
        </Link>
      </Tooltip>
      <nav className={styles.sidebarNav}>
        {NAV_ITEMS.map(({ to, label, icon: Icon, tone, end }) => (
          // When collapsed the item is icon-only, so the tooltip names it; when
          // labels are visible the hint would be redundant, so it's switched off.
          <Tooltip key={to} label={showLabels ? '' : label} side="right">
            {/* Plain string className (not a function): Radix's `asChild` on the
                Tooltip only merges string classes, and NavLink marks the active
                route with aria-current="page", which the CSS targets directly. */}
            <NavLink to={to} end={end} className={styles.navItem} onClick={onCloseDrawer}>
              <span className={styles.navIcon} data-tone={tone} aria-hidden="true">
                <Icon size={17} strokeWidth={2} />
              </span>
              {showLabels && <span>{label}</span>}
            </NavLink>
          </Tooltip>
        ))}
        {showLabels && <div className={styles.sidebarSectionLabel}>Recent projects</div>}
        <ProjectSwitcher expanded={showLabels} />
      </nav>
      <div className={styles.sidebarFooter}>
        <Tooltip label={expanded ? 'Collapse sidebar' : 'Expand sidebar'} side="right">
          <button className={styles.sidebarToggle} onClick={onToggle} aria-label="Toggle sidebar">
            {expanded ? <ChevronsLeft size={20} /> : <ChevronsRight size={20} />}
            {expanded && <span>Collapse</span>}
          </button>
        </Tooltip>
      </div>
    </aside>
  )
}
