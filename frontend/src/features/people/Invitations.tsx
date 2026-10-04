import { formatDistanceToNow } from 'date-fns'
import { MailPlus } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './Invitations.module.css'
import { extractErrorMessage } from '@/api/errors'
import {
  type InvitationRole,
  type SentInvitation,
  useCreateInvitation,
  useInvitations,
  useResendInvitation,
  useRevokeInvitation,
} from '@/api/invitations'
import { useTeams } from '@/api/teams'
import { Button, CopyButton, Dialog, DialogContent, Input } from '@/design-system'

const STATUS_LABELS = { pending: 'Pending', accepted: 'Joined', revoked: 'Revoked', expired: 'Expired' } as const

/** The link of an invitation that was just sent or resent (links aren't stored, so they can only
 * be shown at that moment), with whether the email went out. */
function SentLink({ sent }: { sent: SentInvitation }) {
  return (
    <div className={styles.sent} role="status">
      <div>
        {sent.email_sent
          ? `Invitation emailed to ${sent.email}.`
          : `The email to ${sent.email} couldn't be sent. Share this link with them instead:`}{' '}
        The link works once and expires in 7 days.
      </div>
      <div className={styles.linkRow}>
        <code className={styles.link}>{sent.invite_url}</code>
        <CopyButton value={sent.invite_url} label="invitation link" />
      </div>
    </div>
  )
}

export function InviteButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
        <MailPlus size={14} /> Invite people
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Invite someone" maxWidth={480}>
          {open && <InviteForm onDone={() => setOpen(false)} />}
        </DialogContent>
      </Dialog>
    </>
  )
}

function InviteForm({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<InvitationRole>('worker')
  const [teamId, setTeamId] = useState('')
  const { data: teams } = useTeams()
  const create = useCreateInvitation()

  if (create.data) {
    return (
      <div className={styles.form}>
        <SentLink sent={create.data} />
        <div className={styles.actions}>
          <Button variant="subtle" onClick={() => create.reset()}>
            Invite another
          </Button>
          <Button variant="primary" onClick={onDone}>
            Done
          </Button>
        </div>
      </div>
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate({ email: email.trim(), role, team_id: teamId ? Number(teamId) : null })
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <Input
        id="invite-email"
        label="Email"
        type="email"
        required
        autoFocus
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <label className={styles.field}>
        <span>Role</span>
        <select value={role} onChange={(e) => setRole(e.target.value as InvitationRole)}>
          <option value="worker">Worker</option>
          <option value="admin">Admin (organisation admin)</option>
        </select>
      </label>
      <label className={styles.field}>
        <span>Workspace (optional)</span>
        <select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">No workspace</option>
          {teams?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      {create.isError && (
        <div role="alert" className={styles.error}>
          {extractErrorMessage(create.error)}
        </div>
      )}
      <div className={styles.actions}>
        <Button type="button" variant="subtle" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={!email.trim() || create.isPending}>
          {create.isPending ? 'Sending…' : 'Send invitation'}
        </Button>
      </div>
    </form>
  )
}

/** Admins: everyone invited, with resend and revoke for those not yet joined. */
export function InvitationList() {
  const { data: invitations, isLoading } = useInvitations()
  const resend = useResendInvitation()
  const revoke = useRevokeInvitation()
  const [lastSent, setLastSent] = useState<SentInvitation | null>(null)

  if (isLoading || !invitations?.length) return null
  return (
    <section className={styles.list} aria-label="Invitations">
      <h2 className={styles.heading}>Invitations</h2>
      {lastSent && <SentLink sent={lastSent} />}
      {(resend.isError || revoke.isError) && (
        <div role="alert" className={styles.error}>
          {extractErrorMessage(resend.error ?? revoke.error)}
        </div>
      )}
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Workspace</th>
            <th>Status</th>
            <th>Sent</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {invitations.map((inv) => (
            <tr key={inv.id}>
              <td>{inv.email}</td>
              <td>{inv.role === 'admin' ? 'Admin' : 'Worker'}</td>
              <td>{inv.team_name ?? '—'}</td>
              <td>
                <span className={styles.status} data-status={inv.status}>
                  {STATUS_LABELS[inv.status]}
                </span>
                {inv.status === 'pending' && (
                  <span className={styles.expiry}>
                    {' '}
                    · expires {formatDistanceToNow(new Date(inv.expires_at), { addSuffix: true })}
                  </span>
                )}
              </td>
              <td>{formatDistanceToNow(new Date(inv.sent_at), { addSuffix: true })}</td>
              <td className={styles.rowActions}>
                {(inv.status === 'pending' || inv.status === 'expired') && (
                  <Button
                    size="sm"
                    variant="subtle"
                    disabled={resend.isPending}
                    onClick={() => resend.mutate(inv.id, { onSuccess: setLastSent })}
                  >
                    Resend
                  </Button>
                )}
                {inv.status === 'pending' && (
                  <Button size="sm" variant="subtle" disabled={revoke.isPending} onClick={() => revoke.mutate(inv.id)}>
                    Revoke
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
