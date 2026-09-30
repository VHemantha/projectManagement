import {
  Calendar,
  ChevronsLeft,
  ChevronsRight,
  ClipboardList,
  LayoutDashboard,
  ListTodo,
  Settings,
  SquareKanban,
} from 'lucide-react'
import { Navigate, NavLink, Outlet, useLocation, useParams } from 'react-router-dom'

import styles from './ProjectLayout.module.css'
import { useProject } from '@/api/projects'
import { PlaceholderPage } from '@/app/PlaceholderPage'
import rail from '@/app/SideRail.module.css'
import { Tooltip } from '@/design-system'
import { usePanel } from '@/store/sidebarStore'

export function ProjectLayout() {
  const { key } = useParams<{ key: string }>()
  const location = useLocation()
  const { data: project, isLoading } = useProject(key)
  // The project menu collapses to an icon rail like the main sidebar (remembered).
  const panel = usePanel('projectNav')

  if (isLoading) return <PlaceholderPage title="Loading project…" />
  if (!project) return <PlaceholderPage title="Project not found" />
  // Opened by an old key (the project was renamed) or in different letter case.
  if (key !== project.key) {
    const rest = location.pathname.slice(`/projects/${key}`.length)
    return <Navigate replace to={`/projects/${project.key}${rest}${location.search}`} />
  }

  const base = `/projects/${project.key}`
  const navItems = [
    { to: base, label: 'Summary', icon: LayoutDashboard, end: true },
    { to: `${base}/board`, label: project.project_type === 'scrum' ? 'Sprint board' : 'Board', icon: SquareKanban },
    ...(project.project_type === 'scrum'
      ? [{ to: `${base}/backlog`, label: 'Backlog', icon: ListTodo }]
      : []),
    { to: `${base}/timeline`, label: 'Timeline', icon: Calendar },
    { to: `${base}/issues`, label: 'Jobs', icon: ClipboardList },
    { to: `${base}/reports`, label: 'Reports', icon: LayoutDashboard },
    { to: `${base}/settings`, label: 'Project settings', icon: Settings },
  ]

  return (
    <div className={styles.layout}>
      <aside
        className={`${styles.sidebar} ${panel.open ? '' : styles.collapsed}`}
        aria-label={`${project.name} menu`}
      >
        <div className={styles.header}>
          <Tooltip label={panel.open ? '' : `${project.name} (${project.key})`} side="right">
            <span className={styles.projectAvatar} style={{ background: project.avatar_color }}>
              {project.key.slice(0, 2).toUpperCase()}
            </span>
          </Tooltip>
          <div className={styles.headerText}>
            <div className={styles.projectName}>{project.name}</div>
            <div className={styles.projectType}>{project.project_type} project</div>
          </div>
        </div>
        <nav className={styles.nav}>
          {navItems.map(({ to, label, icon: Icon, end }) => (
            // Collapsed: icon only, named by its tooltip (like the main sidebar).
            <Tooltip key={to} label={panel.open ? '' : label} side="right">
              <NavLink to={to} end={end} className={styles.navItem} aria-label={label}>
                <Icon size={16} strokeWidth={1.75} />
                <span className={styles.navLabel}>{label}</span>
              </NavLink>
            </Tooltip>
          ))}
        </nav>
        <div className={styles.footer}>
          <Tooltip label={panel.open ? 'Collapse menu' : 'Expand menu'} side="right">
            <button
              type="button"
              className={rail.toggle}
              onClick={panel.toggle}
              aria-label={panel.open ? 'Collapse project menu' : 'Expand project menu'}
            >
              {panel.open ? <ChevronsLeft size={18} /> : <ChevronsRight size={18} />}
            </button>
          </Tooltip>
        </div>
      </aside>
      <div className={styles.content}>
        <Outlet context={{ project }} />
      </div>
    </div>
  )
}
