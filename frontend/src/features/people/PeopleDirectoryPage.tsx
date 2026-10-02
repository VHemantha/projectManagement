import { LayoutGrid, Network } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { InvitationList, InviteButton } from './Invitations'
import { OrgChart } from './OrgChart'
import styles from './PeopleDirectoryPage.module.css'
import { useUserHierarchy, useUsers } from '@/api/users'
import { Avatar, CopyButton } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

type View = 'list' | 'diagram'

export function PeopleDirectoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const view: View = searchParams.get('view') === 'diagram' ? 'diagram' : 'list'
  const { data: users, isLoading } = useUsers()
  const { data: hierarchy, isLoading: hierarchyLoading } = useUserHierarchy(view === 'diagram')
  const navigate = useNavigate()
  const isAdmin = useAuthStore((s) => !!s.user?.is_staff)

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>People</h1>
        {isAdmin && <InviteButton />}
        <div className={styles.viewToggle} role="group" aria-label="View">
          <button
            type="button"
            aria-pressed={view === 'list'}
            onClick={() => setSearchParams({}, { replace: true })}
          >
            <LayoutGrid size={14} aria-hidden="true" /> List
          </button>
          <button
            type="button"
            aria-pressed={view === 'diagram'}
            onClick={() => setSearchParams({ view: 'diagram' }, { replace: true })}
          >
            <Network size={14} aria-hidden="true" /> Diagram
          </button>
        </div>
      </div>
      {isAdmin && view === 'list' && <InvitationList />}
      {view === 'diagram' ? (
        hierarchyLoading || !hierarchy ? (
          <div>Loading…</div>
        ) : (
          <OrgChart hierarchy={hierarchy} />
        )
      ) : isLoading ? (
        <div>Loading…</div>
      ) : (
        <div className={styles.grid}>
          {users?.map((user) => (
            <div key={user.id} className={styles.card} onClick={() => navigate(`/people/${user.id}`)}>
              <Avatar name={user.display_name} src={user.avatar} size={44} userId={user.id} interactive />
              <div className={styles.info}>
                <div className={styles.name}>{user.display_name}</div>
                {user.job_title && <div className={styles.role}>{user.job_title}</div>}
                <div className={styles.emailRow}>
                  {/* mailto link + copy button; both stop the click from opening
                      the person page so the email actions work in isolation. */}
                  <a
                    className={styles.email}
                    href={`mailto:${user.email}`}
                    title={user.email}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {user.email}
                  </a>
                  <CopyButton value={user.email} label="email" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
