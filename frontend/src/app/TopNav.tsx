import { HelpCircle, Plus, Search } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import styles from './AppShell.module.css'
import { GlobalTimerWidget } from './GlobalTimerWidget'
import { useLogout } from '@/api/auth'
import { NotificationBell } from '@/features/notifications/NotificationBell'
import { useAuthStore } from '@/store/authStore'
import { useUiStore } from '@/store/uiStore'
import {
  Avatar,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/design-system'

export function TopNav() {
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()
  const navigate = useNavigate()
  const openCreateIssue = useUiStore((s) => s.openCreateIssue)
  const toggleQuickSearch = useUiStore((s) => s.toggleQuickSearch)

  return (
    <header className={styles.topnav}>
      <div className={styles.topnavLeft}>
        <button
          className={styles.iconBtn}
          style={{ background: 'var(--tf-blue)', color: '#fff', borderRadius: 'var(--tf-radius-md)', width: 'auto', padding: '0 12px', display: 'flex', gap: 4 }}
          onClick={() => openCreateIssue()}
        >
          <Plus size={16} />
          <span style={{ fontSize: 14, fontWeight: 500 }}>Create</span>
        </button>
      </div>

      <div className={styles.topnavSearch}>
        <div className={styles.searchInput} onClick={toggleQuickSearch}>
          <Search size={15} />
          <span>Search issues, projects…</span>
          <kbd className={styles.searchKbd}>Ctrl K</kbd>
        </div>
      </div>

      <div className={styles.topnavRight}>
        <GlobalTimerWidget />
        <button className={styles.iconBtn} aria-label="Help">
          <HelpCircle size={18} />
        </button>
        <NotificationBell />
        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className={styles.avatarBtn} aria-label="Account menu">
                <Avatar name={user.display_name} src={user.avatar} size={32} />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuLabel>{user.display_name}</DropdownMenuLabel>
              <DropdownMenuItem onSelect={() => navigate('/profile')}>Profile</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={logout}>Log out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  )
}
