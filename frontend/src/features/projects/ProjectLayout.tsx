import {
  Calendar,
  ClipboardList,
  LayoutDashboard,
  ListTodo,
  Settings,
  SquareKanban,
} from 'lucide-react'
import { NavLink, Outlet, useParams } from 'react-router-dom'

import styles from './ProjectLayout.module.css'
import { useProject } from '@/api/projects'
import { PlaceholderPage } from '@/app/PlaceholderPage'

export function ProjectLayout() {
  const { key } = useParams<{ key: string }>()
  const { data: project, isLoading } = useProject(key)

  if (isLoading) return <PlaceholderPage title="Loading project…" />
  if (!project) return <PlaceholderPage title="Project not found" />

  const base = `/projects/${project.key}`
  const navItems = [
    { to: base, label: 'Summary', icon: LayoutDashboard, end: true },
    { to: `${base}/board`, label: project.project_type === 'scrum' ? 'Sprint board' : 'Board', icon: SquareKanban },
    ...(project.project_type === 'scrum'
      ? [{ to: `${base}/backlog`, label: 'Backlog', icon: ListTodo }]
      : []),
    { to: `${base}/timeline`, label: 'Timeline', icon: Calendar },
    { to: `${base}/issues`, label: 'Issues', icon: ClipboardList },
    { to: `${base}/reports`, label: 'Reports', icon: LayoutDashboard },
    { to: `${base}/settings`, label: 'Project settings', icon: Settings },
  ]

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.header}>
          <span className={styles.projectAvatar} style={{ background: project.avatar_color }}>
            {project.key.slice(0, 2)}
          </span>
          <div>
            <div className={styles.projectName}>{project.name}</div>
            <div className={styles.projectType}>{project.project_type} project</div>
          </div>
        </div>
        <nav className={styles.nav}>
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
            >
              <Icon size={16} strokeWidth={1.75} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className={styles.content}>
        <Outlet context={{ project }} />
      </div>
    </div>
  )
}
