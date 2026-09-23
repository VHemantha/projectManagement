import { type FormEvent, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import styles from './auth.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useLogin } from '@/api/auth'
import { Button, Input } from '@/design-system'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const login = useLogin()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate(
      { email, password },
      {
        onSuccess: () => {
          const from = (location.state as { from?: string } | null)?.from ?? '/'
          navigate(from, { replace: true })
        },
      },
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>T</span>
          <span className={styles.logoText}>TrackFlow</span>
        </div>
        <h1 className={styles.title}>Log in to your account</h1>
        <form className={styles.form} onSubmit={handleSubmit}>
          {login.isError && (
            <div className={styles.formError}>{extractErrorMessage(login.error)}</div>
          )}
          <Input
            id="email"
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            id="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button
            type="submit"
            variant="primary"
            className={styles.submit}
            disabled={login.isPending}
          >
            {login.isPending ? 'Logging in…' : 'Log in'}
          </Button>
        </form>
        <div className={styles.footer}>
          Don&apos;t have an account? <Link to="/signup">Sign up</Link>
        </div>
      </div>
      {/* Company attribution — a small "powered by" credit with the current
          copyright year, generated at render time so it never goes stale. */}
      <div className={styles.brandCredit}>
        Powered by <strong>AXISPEX&nbsp;Ltd</strong> &middot; &copy; {new Date().getFullYear()}
      </div>
    </div>
  )
}
