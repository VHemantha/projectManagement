import { BellRing, X } from 'lucide-react'
import { useState } from 'react'

import styles from './DesktopNotifications.module.css'
import {
  desktopPermission,
  dismissDesktopOffer,
  requestDesktopPermission,
  shouldOfferDesktopNotifications,
} from './desktopNotifications'
import { useUpdateMySettings } from '@/api/auth'
import { Button } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

/** A one-time offer, shown just after login (never on a plain page load), to let the browser
 * show desktop notifications. */
export function DesktopNotificationsPrompt() {
  const enabled = useAuthStore((s) => s.user?.desktop_notifications ?? true)
  const [visible, setVisible] = useState(() => {
    const offer = shouldOfferDesktopNotifications(enabled)
    // Offered once per login: it stays up while the app is open, but not after a reload.
    if (offer) dismissDesktopOffer(false)
    return offer
  })
  if (!visible) return null

  return (
    <div className={styles.prompt} role="region" aria-label="Desktop notifications">
      <span className={styles.promptIcon} aria-hidden="true">
        <BellRing size={16} />
      </span>
      <span className={styles.promptText}>
        Get a desktop notification when someone messages or mentions you, even when TrackFlow is in the
        background.
      </span>
      <Button
        size="sm"
        variant="primary"
        onClick={async () => {
          await requestDesktopPermission()
          dismissDesktopOffer(false)
          setVisible(false)
        }}
      >
        Turn on
      </Button>
      <Button
        size="sm"
        variant="subtle"
        onClick={() => {
          dismissDesktopOffer(true)
          setVisible(false)
        }}
      >
        Not now
      </Button>
      <button
        type="button"
        className={styles.close}
        aria-label="Close"
        onClick={() => {
          dismissDesktopOffer(false)
          setVisible(false)
        }}
      >
        <X size={14} />
      </button>
    </div>
  )
}

/** Profile setting: the person's own on/off switch, plus what the browser currently allows. */
export function DesktopNotificationSetting() {
  const enabled = useAuthStore((s) => s.user?.desktop_notifications ?? true)
  const setUser = useAuthStore((s) => s.setUser)
  const update = useUpdateMySettings()
  const [permission, setPermission] = useState(desktopPermission)

  const browserNote =
    permission === 'unsupported'
      ? "This browser can't show desktop notifications."
      : permission === 'denied'
        ? 'Your browser is blocking notifications from TrackFlow. Allow them in the site settings (the icon left of the address) to see them.'
        : permission === 'default' && enabled
          ? 'Your browser will ask for permission.'
          : null

  return (
    <div className={styles.setting}>
      <label className={styles.toggle}>
        <input
          type="checkbox"
          checked={enabled}
          onChange={async (e) => {
            const on = e.target.checked
            const user = useAuthStore.getState().user
            // Flip straight away; put it back if saving fails.
            if (user) setUser({ ...user, desktop_notifications: on })
            update.mutate(
              { desktop_notifications: on },
              { onError: () => user && setUser({ ...user, desktop_notifications: !on }) },
            )
            if (on && desktopPermission() === 'default') setPermission(await requestDesktopPermission())
          }}
        />
        <span>
          <strong>Desktop notifications</strong>
          <span className={styles.settingHint}>
            New direct messages, @mentions and bell notifications. Not your own messages, and not while the
            chat is open in front of you.
          </span>
        </span>
      </label>
      {enabled && permission === 'default' && (
        <Button size="sm" variant="subtle" onClick={async () => setPermission(await requestDesktopPermission())}>
          Allow in this browser
        </Button>
      )}
      {browserNote && <p className={styles.settingHint}>{browserNote}</p>}
    </div>
  )
}
