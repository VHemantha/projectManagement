import { type FormEvent, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import styles from './auth.module.css'
import { useSignup } from '@/api/auth'
import { extractErrorMessage } from '@/api/errors'
import { useInvitationPreview } from '@/api/invitations'
import { Button, Input } from '@/design-system'

/** Sign-up is by invitation only: this page works from an invitation link
 * (/signup?invite=…), with the email fixed to the invited address. */
export function SignupPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('invite')
  const preview = useInvitationPreview(token)
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const signup = useSignup()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!token) return
    signup.mutate(
      { invite_token: token, username, password, display_name: displayName },
      { onSuccess: () => navigate('/', { replace: true }) },
    )
  }

  const blocked = !token
    ? 'Sign-up is by invitation only. Ask an admin to invite you, then use the link in the email.'
    : preview.isError
      ? extractErrorMessage(preview.error, 'This invitation link is not valid.')
      : null

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>T</span>
          <span className={styles.logoText}>TrackFlow</span>
        </div>
        <h1 className={styles.title}>Create your account</h1>
        {blocked ? (
          <div className={styles.formError} role="alert">
            {blocked}
          </div>
        ) : preview.isLoading || !preview.data ? (
          <p>Checking your invitation…</p>
        ) : (
          <form className={styles.form} onSubmit={handleSubmit}>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--tf-text-subtle)' }}>
              {preview.data.invited_by_name ?? 'An admin'} invited you to join as{' '}
              {preview.data.role === 'admin' ? 'an admin' : 'a worker'}
              {preview.data.team_name ? ` in the ${preview.data.team_name} team` : ''}.
            </p>
            {signup.isError && <div className={styles.formError}>{extractErrorMessage(signup.error)}</div>}
            <Input id="email" label="Email" type="email" value={preview.data.email} disabled readOnly />
            <Input
              id="display_name"
              label="Full name"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
            <Input id="username" label="Username" required value={username} onChange={(e) => setUsername(e.target.value)} />
            <Input
              id="password"
              label="Password"
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" variant="primary" className={styles.submit} disabled={signup.isPending}>
              {signup.isPending ? 'Creating account…' : 'Create account'}
            </Button>
          </form>
        )}
        <div className={styles.footer}>
          Already have an account? <Link to="/login">Log in</Link>
        </div>
      </div>
    </div>
  )
}
