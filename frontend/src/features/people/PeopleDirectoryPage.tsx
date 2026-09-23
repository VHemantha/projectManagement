import { useNavigate } from 'react-router-dom'

import styles from './PeopleDirectoryPage.module.css'
import { useUsers } from '@/api/users'
import { Avatar, CopyButton } from '@/design-system'

export function PeopleDirectoryPage() {
  const { data: users, isLoading } = useUsers()
  const navigate = useNavigate()

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>People</h1>
      {isLoading ? (
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
