import { useNavigate } from 'react-router-dom'

import styles from './PeopleDirectoryPage.module.css'
import { useUsers } from '@/api/users'
import { Avatar } from '@/design-system'

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
              <Avatar name={user.display_name} src={user.avatar} size={40} />
              <div>
                <div className={styles.name}>{user.display_name}</div>
                <div className={styles.role}>{user.job_title || user.email}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
