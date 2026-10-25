import { Navigate } from 'react-router-dom'

import styles from './Coordinator.module.css'
import { useCoordinatorMe } from '@/api/coordinator'
import { Skeleton } from '@/design-system'

/** /coordinator — opens the person's own conversation with the Loca Coordinator in Messages
 * (created on first visit, with a welcome from the agent). */
export function CoordinatorChatRedirect() {
  const { data, isError } = useCoordinatorMe()
  if (isError) return <p className={styles.error}>The coordinator could not be opened. Refresh the page to try again.</p>
  if (!data) return <Skeleton height={64} />
  return <Navigate to={`/chat?channel=${data.conversation_id}`} replace />
}
