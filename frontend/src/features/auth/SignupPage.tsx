import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import styles from './auth.module.css'
import { extractErrorMessage } from '@/api/errors'
import { useSignup } from '@/api/auth'
import { Button, Input } from '@/design-system'

export function SignupPage() {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const signup = useSignup()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    signup.mutate(
      { email, username, password, display_name: displayName },
      { onSuccess: () => navigate('/', { replace: true }) },
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>T</span>
          <span className={styles.logoText}>TrackFlow</span>
        </div>
        <h1 className={styles.title}>Create your account</h1>
        <form className={styles.form} onSubmit={handleSubmit}>
          {signup.isError && (
            <div className={styles.formError}>{extractErrorMessage(signup.error)}</div>
          )}
          <Input
            id="display_name"
            label="Full name"
            required
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
          <Input
            id="username"
            label="Username"
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
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
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button
            type="submit"
            variant="primary"
            className={styles.submit}
            disabled={signup.isPending}
          >
            {signup.isPending ? 'Creating account…' : 'Sign up'}
          </Button>
        </form>
        <div className={styles.footer}>
          Already have an account? <Link to="/login">Log in</Link>
        </div>
      </div>
    </div>
  )
}
