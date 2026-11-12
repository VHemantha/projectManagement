import { Building2, Check, FolderKanban, Layers, Search, Users } from 'lucide-react'
import { type ReactNode, useRef, useState } from 'react'

import styles from './OrganisationNames.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type Renamable, useOrganisation, useOrganisationNames, useRename } from '@/api/organisation'
import { Avatar, Skeleton } from '@/design-system'

/** The CEO's Names tab (AFIT, 12 Nov 2026): every name in the organisation in one place — the
 * organisation itself, its people (name and job title), workspaces, sub-workspaces and projects.
 * A name saves when you press Enter or leave the box; Escape puts it back. Each change is logged. */
export function OrganisationNames() {
  const { data: org } = useOrganisation()
  const { data, isLoading } = useOrganisationNames()
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const has = (...texts: (string | null | undefined)[]) => !q || texts.some((t) => t?.toLowerCase().includes(q))

  if (isLoading || !data || !org) return <Skeleton height={240} />

  const people = data.people.filter((p) => has(p.display_name, p.job_title, p.email))
  const teams = data.teams.filter((t) => has(t.name, t.parent?.name))
  const clients = data.clients.filter((c) => has(c.name, c.team_name))
  const projects = data.projects.filter((p) => has(p.name, p.key, p.client?.name))

  return (
    <div className={styles.names}>
      <p className={styles.lead}>
        Rename anything in the organisation. A name saves when you press Enter or click away; Escape puts it back. Project keys
        (and so task keys) stay as they are. Every change is in the audit log.
      </p>
      <label className={styles.search}>
        <Search size={16} aria-hidden="true" />
        <input
          aria-label="Find a name"
          placeholder="Find a person, workspace, sub-workspace or project…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      <Section icon={<Building2 size={18} />} title="Organisation">
        <Row hint="Shown in the sidebar under TASKO">
          <NameField kind="organisation" id={org.id} field="name" value={org.name} label="Organisation name" />
        </Row>
      </Section>

      <Section icon={<Users size={18} />} title="People" count={people.length}>
        {people.map((p) => (
          <Row key={p.id} label={<Avatar name={p.display_name} src={p.avatar} size={28} />} hint={p.email}>
            <NameField kind="person" id={p.id} field="display_name" value={p.display_name} label={`Name of ${p.email}`} />
            <NameField
              kind="person"
              id={p.id}
              field="job_title"
              value={p.job_title}
              label={`Job title of ${p.email}`}
              placeholder="Job title"
              optional
            />
          </Row>
        ))}
      </Section>

      <Section icon={<Layers size={18} />} title="Workspaces" count={teams.length}>
        {teams.map((t) => (
          <Row key={t.id} label={<span className={styles.swatch} style={{ background: t.avatar_color }} />} hint={t.parent ? `In ${t.parent.name}` : 'Top level'}>
            <NameField kind="team" id={t.id} field="name" value={t.name} label={`Name of workspace ${t.name}`} />
          </Row>
        ))}
      </Section>

      <Section icon={<Layers size={18} />} title="Sub-workspaces" count={clients.length}>
        {clients.map((c) => (
          <Row key={c.id} hint={c.team_name ? `In ${c.team_name}` : 'Not in a workspace'}>
            <NameField kind="client" id={c.id} field="name" value={c.name} label={`Name of sub-workspace ${c.name}`} />
          </Row>
        ))}
      </Section>

      <Section icon={<FolderKanban size={18} />} title="Projects" count={projects.length}>
        {projects.map((p) => (
          <Row
            key={p.id}
            label={<span className={styles.key}>{p.key}</span>}
            hint={p.is_client_workspace ? `Tasks without a project${p.client ? ` · ${p.client.name}` : ''}` : (p.client?.name ?? 'No sub-workspace')}
          >
            <NameField kind="project" id={p.key} field="name" value={p.name} label={`Name of project ${p.key}`} />
          </Row>
        ))}
      </Section>
    </div>
  )
}

function Section({ icon, title, count, children }: { icon: ReactNode; title: string; count?: number; children: ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h3 className={styles.sectionTitle}>
        <span className={styles.sectionIcon} aria-hidden="true">
          {icon}
        </span>
        {title}
        {count !== undefined && <span className={styles.count}>{count}</span>}
      </h3>
      {count === 0 ? <p className={styles.muted}>Nothing matches.</p> : <div className={styles.rows}>{children}</div>}
    </section>
  )
}

function Row({ label, hint, children }: { label?: ReactNode; hint?: string; children: ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      <div className={styles.fields}>{children}</div>
      {hint && <span className={styles.hint}>{hint}</span>}
    </div>
  )
}

function NameField({ kind, id, field, value, label, placeholder, optional }: {
  kind: Renamable
  id: number | string
  field: string
  value: string
  label: string
  placeholder?: string
  optional?: boolean
}) {
  const rename = useRename(kind)
  const [draft, setDraft] = useState(value)
  const [saved, setSaved] = useState(false)
  // Escape puts the name back and leaves the box; leaving must then not save what was typed.
  const cancelled = useRef(false)
  // A change made elsewhere (another tab, another person) shows here unless you are typing.
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    setDraft(value)
  }

  const save = () => {
    if (cancelled.current) {
      cancelled.current = false
      return setDraft(value)
    }
    const next = draft.split(/\s+/).filter(Boolean).join(' ')
    if (next === value) return setDraft(value)
    if (!next && !optional) return setDraft(value)
    rename.mutate(
      { id, body: { [field]: next } },
      { onSuccess: () => (setSaved(true), setTimeout(() => setSaved(false), 1800)), onError: () => setDraft(value) },
    )
  }

  return (
    <span className={styles.field}>
      <input
        aria-label={label}
        value={draft}
        placeholder={placeholder}
        maxLength={150}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur()
          if (e.key === 'Escape') {
            cancelled.current = true
            setDraft(value)
            e.currentTarget.blur()
          }
        }}
      />
      {saved && (
        <span className={styles.saved} role="status">
          <Check size={14} aria-hidden="true" /> Saved
        </span>
      )}
      {rename.isError && (
        <span className={styles.error} role="alert">
          {extractErrorMessage(rename.error)}
        </span>
      )}
    </span>
  )
}
