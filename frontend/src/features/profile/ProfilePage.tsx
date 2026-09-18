import { type FormEvent, useRef, useState } from 'react'

import styles from './ProfilePage.module.css'
import { useUpdateProfile } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { Avatar, Button, Input } from '@/design-system'

export function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const updateProfile = useUpdateProfile()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [displayName, setDisplayName] = useState(user?.display_name ?? '')
  const [jobTitle, setJobTitle] = useState(user?.job_title ?? '')
  const [avatarFile, setAvatarFile] = useState<File | null>(null)
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null)

  if (!user) return null

  const handleAvatarPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAvatarFile(file)
    setAvatarPreview(URL.createObjectURL(file))
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const form = new FormData()
    form.append('display_name', displayName)
    form.append('job_title', jobTitle)
    if (avatarFile) form.append('avatar', avatarFile)
    updateProfile.mutate(form)
  }

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Your profile</h1>
      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.avatarRow}>
          <Avatar name={displayName || user.display_name} src={avatarPreview ?? user.avatar} size={64} />
          <div>
            <Button type="button" variant="secondary" onClick={() => fileInputRef.current?.click()}>
              Change avatar
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={handleAvatarPick}
            />
          </div>
        </div>
        <div className={styles.meta}>{user.email}</div>
        <Input
          id="display_name"
          label="Display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
        <Input
          id="job_title"
          label="Job title"
          value={jobTitle}
          onChange={(e) => setJobTitle(e.target.value)}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button type="submit" variant="primary" disabled={updateProfile.isPending}>
            {updateProfile.isPending ? 'Saving…' : 'Save changes'}
          </Button>
          {updateProfile.isSuccess && <span className={styles.savedMsg}>Saved</span>}
        </div>
      </form>
    </div>
  )
}
