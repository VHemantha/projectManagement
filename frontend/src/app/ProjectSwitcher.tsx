import { NavLink } from 'react-router-dom'

import styles from './AppShell.module.css'
import { useProjects } from '@/api/projects'

// Shows the most recently updated projects. Real Jira also tracks explicit
// "starred" projects; that needs a favorites model we haven't added yet, so
// this is recency-based for now.
export function ProjectSwitcher({ expanded }: { expanded: boolean }) {
  const { data: projects } = useProjects()

  if (!expanded) return null

  const recent = [...(projects ?? [])]
    .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
    .slice(0, 5)

  if (recent.length === 0) {
    return (
      <div
        className={styles.sidebarSectionLabel}
        style={{ opacity: 0.6, textTransform: 'none', fontWeight: 400 }}
      >
        No projects yet
      </div>
    )
  }

  return (
    <>
      {recent.map((project) => (
        <NavLink
          key={project.id}
          to={`/projects/${project.key}`}
          className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
        >
          <span
            style={{
              width: 18,
              height: 18,
              borderRadius: 3,
              background: project.avatar_color,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              fontWeight: 700,
              flexShrink: 0,
            }}
          >
            {project.key.slice(0, 1)}
          </span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {project.name}
          </span>
        </NavLink>
      ))}
    </>
  )
}
