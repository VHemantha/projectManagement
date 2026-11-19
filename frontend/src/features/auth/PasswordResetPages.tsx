import { type FormEvent, type ReactNode, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import styles from './auth.module.css'
import { useConfirmPasswordReset, useRequestPasswordReset } from '@/api/auth'
import { extractErrorMessage } from '@/api/errors'
import { Button, Input } from '@/design-system'

function AuthCard({ title, children, footer }: { title: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.logo}>
          <span className={styles.logoMark}>L</span>
          <span className={styles.logoText}>TASKO</span>
        </div>
        <h1 className={styles.title}>{title}</h1>
        {children}
        <div className={styles.footer}>{footer}</div>
      </div>
    </div>
  )
}

/** /forgot-password: email me a link to set a new password (18 Nov 2026). */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const request = useRequestPasswordReset()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    request.mutate({ email })
  }

  return (
    <AuthCard title="Reset your password" footer={<Link to="/login">Back to log in</Link>}>
      {request.isSuccess ? (
        <p role="status">{request.data.detail}</p>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          {request.isError && <div className={styles.formError}>{extractErrorMessage(request.error)}</div>}
          <Input id="email" label="Email" type="email" autoComplete="email" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" variant="primary" className={styles.submit} disabled={request.isPending}>
            {request.isPending ? 'Sending…' : 'Email me a link'}
          </Button>
        </form>
      )}
    </AuthCard>
  )
}

/** /reset-password?uid=…&token=…: set a new password with the emailed link. */
export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [mismatch, setMismatch] = useState(false)
  const confirm = useConfirmPasswordReset()

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (password !== again) {
      setMismatch(true)
      return
    }
    setMismatch(false)
    confirm.mutate({ uid, token, password })
  }

  if (!uid || !token) {
    return (
      <AuthCard title="Set a new password" footer={<Link to="/forgot-password">Ask for a new link</Link>}>
        <div className={styles.formError} role="alert">This link is incomplete. Open the link from your email again, or ask for a new one.</div>
      </AuthCard>
    )
  }
  return (
    <AuthCard title="Set a new password" footer={<Link to="/login">Back to log in</Link>}>
      {confirm.isSuccess ? (
        <p role="status">
          {confirm.data.detail} <Link to="/login">Log in</Link>
        </p>
      ) : (
        <form className={styles.form} onSubmit={handleSubmit}>
          {(mismatch || confirm.isError) && (
            <div className={styles.formError} role="alert">
              {mismatch ? "The two passwords don't match." : extractErrorMessage(confirm.error)}
            </div>
          )}
          <Input id="password" label="New password" type="password" autoComplete="new-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
          <Input id="password-again" label="New password again" type="password" autoComplete="new-password" required value={again}
            onChange={(e) => setAgain(e.target.value)} />
          <Button type="submit" variant="primary" className={styles.submit} disabled={confirm.isPending}>
            {confirm.isPending ? 'Saving…' : 'Set password'}
          </Button>
        </form>
      )}
    </AuthCard>
  )
}
