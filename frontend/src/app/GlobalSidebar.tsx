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
import { NavLink } from 'react-router-dom'

import styles from './AppShell.module.css'
import { ProjectSwitcher } from './ProjectSwitcher'

const NAV_ITEMS = [
  { to: '/', label: 'Your work', icon: UserRound, end: true },
  { to: '/projects', label: 'Projects', icon: LayoutGrid },
  { to: '/teams', label: 'Teams', icon: Users },
  { to: '/people', label: 'People', icon: Contact },
  { to: '/filters', label: 'Filters', icon: ListFilter },
  { to: '/dashboards', label: 'Dashboards', icon: LayoutDashboard },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/timesheets', label: 'Timesheets', icon: Clock },
  { to: '/apps', label: 'Apps', icon: Grid3x3 },
]

interface GlobalSidebarProps {
  expanded: boolean
  onToggle: () => void
}

export function GlobalSidebar({ expanded, onToggle }: GlobalSidebarProps) {
  return (
    <aside className={`${styles.sidebar} ${expanded ? styles.expanded : ''}`}>
      <div className={styles.sidebarHeader}>
        <span className={styles.sidebarLogoMark}>T</span>
        {expanded && <span className={styles.sidebarLogoText}>TrackFlow</span>}
      </div>
      <nav className={styles.sidebarNav}>
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
          >
            <Icon size={18} strokeWidth={1.75} />
            {expanded && <span>{label}</span>}
          </NavLink>
        ))}
        {expanded && <div className={styles.sidebarSectionLabel}>Recent projects</div>}
        <ProjectSwitcher expanded={expanded} />
      </nav>
      <div className={styles.sidebarFooter}>
        <button className={styles.navItem} onClick={onToggle} aria-label="Toggle sidebar">
          {expanded ? <ChevronsLeft size={18} /> : <ChevronsRight size={18} />}
          {expanded && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}
