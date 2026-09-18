import * as RadixPopover from '@radix-ui/react-popover'
import { formatDistanceToNow } from 'date-fns'
import { Bell } from 'lucide-react'

import navStyles from '@/app/AppShell.module.css'
import styles from './NotificationBell.module.css'
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications, useUnreadCount } from '@/api/notifications'
import type { NotificationItem } from '@/api/types'
import { useUiStore } from '@/store/uiStore'

const VERB_TEXT: Record<NotificationItem['verb'], string> = {
  assigned: 'assigned you',
  mentioned: 'mentioned you on',
  commented: 'commented on',
  status_changed: 'changed the status of',
  watching_updated: 'updated',
}

export function NotificationBell() {
  const { data: notifications } = useNotifications()
  const { data: unreadCount } = useUnreadCount()
  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllNotificationsRead()
  const openIssueModal = useUiStore((s) => s.openIssueModal)

  const handleClick = (n: NotificationItem) => {
    if (!n.is_read) markRead.mutate(n.id)
    if (n.target_issue_key) openIssueModal(n.target_issue_key)
  }

  return (
    <RadixPopover.Root>
      <RadixPopover.Trigger asChild>
        <button className={navStyles.iconBtn} aria-label="Notifications">
          <Bell size={18} />
          {!!unreadCount && <span className={navStyles.badgeDot} />}
        </button>
      </RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content className={styles.content} align="end" sideOffset={6}>
          <div className={styles.header}>
            <span>Notifications</span>
            {!!unreadCount && (
              <button className={styles.markAll} onClick={() => markAllRead.mutate()}>
                Mark all read
              </button>
            )}
          </div>
          {!notifications || notifications.length === 0 ? (
            <div className={styles.empty}>You&apos;re all caught up.</div>
          ) : (
            notifications.map((n) => (
              <div
                key={n.id}
                className={`${styles.row} ${!n.is_read ? styles.unread : ''}`}
                onClick={() => handleClick(n)}
              >
                {!n.is_read ? <span className={styles.dot} /> : <span className={styles.dotSpacer} />}
                <div className={styles.body}>
                  <div>
                    <strong>{n.actor?.display_name ?? 'Someone'}</strong> {VERB_TEXT[n.verb]}{' '}
                    {n.target_issue_key && (
                      <>
                        <strong>{n.target_issue_key}</strong> {n.target_issue_summary}
                      </>
                    )}
                  </div>
                  <div className={styles.time}>{formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}</div>
                </div>
              </div>
            ))
          )}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  )
}
