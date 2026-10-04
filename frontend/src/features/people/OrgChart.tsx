import { Info, Shield, Users } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { nestTeams, type TeamTree } from './hierarchy'
import styles from './OrgChart.module.css'
import type { HierarchyNode, HierarchyTeam, UserHierarchy } from '@/api/types'
import { Avatar } from '@/design-system'

const ROLE_LABELS: Record<HierarchyNode['role'], string> = { admin: 'Admin', lead: 'Workspace lead', member: 'Member' }

/**
 * The organisation as a diagram: admins on top, then one branch per team with its leads above
 * its members. Plain CSS (flex + connector lines) — a chart this shallow doesn't need a
 * diagram library.
 */
export function OrgChart({ hierarchy }: { hierarchy: UserHierarchy }) {
  const branches = nestTeams(hierarchy.teams)
  return (
    <div className={styles.chart}>
      <p className={styles.basis}>
        <Info size={14} aria-hidden="true" /> {hierarchy.basis}
      </p>
      <div className={styles.tier} role="group" aria-label="Admins">
        <div className={styles.tierLabel}>
          <Shield size={14} aria-hidden="true" /> Admins
        </div>
        <div className={styles.nodes}>
          {hierarchy.admins.length ? (
            hierarchy.admins.map((u) => <PersonNode key={u.id} person={u} />)
          ) : (
            <span className={styles.empty}>No admins</span>
          )}
        </div>
      </div>
      <div className={styles.trunk} aria-hidden="true" />
      <div className={styles.branches}>
        {branches.map((tree) => (
          <section key={tree.team.id} className={styles.branch} aria-label={`${tree.team.name} workspace`}>
            <TeamTreeView tree={tree} />
          </section>
        ))}
        {hierarchy.no_team.length > 0 && (
          <section className={styles.branch} aria-label="No workspace">
            <div className={styles.teamHeader} style={{ borderTopColor: 'var(--tf-border)' }}>
              <Users size={14} aria-hidden="true" /> No workspace
            </div>
            <div className={styles.members}>
              {hierarchy.no_team.map((u) => (
                <PersonNode key={u.id} person={u} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

function TeamTreeView({ tree }: { tree: TeamTree }) {
  return (
    <>
      <TeamBox team={tree.team} />
      {tree.children.length > 0 && (
        <div className={styles.subTeams}>
          {tree.children.map((child) => (
            <section key={child.team.id} className={styles.subTeam} aria-label={`${child.team.name} workspace`}>
              <TeamTreeView tree={child} />
            </section>
          ))}
        </div>
      )}
    </>
  )
}

function TeamBox({ team }: { team: HierarchyTeam }) {
  const empty = team.leads.length === 0 && team.members.length === 0
  return (
    <>
      <div className={styles.teamHeader} style={{ borderTopColor: team.avatar_color }}>
        <span className={styles.teamDot} style={{ background: team.avatar_color }} aria-hidden="true" />
        {team.name}
      </div>
      {team.leads.length > 0 && (
        <div className={styles.leads}>
          {team.leads.map((u) => (
            <PersonNode key={u.id} person={u} />
          ))}
        </div>
      )}
      {team.members.length > 0 && (
        <div className={styles.members}>
          {team.members.map((u) => (
            <PersonNode key={u.id} person={u} />
          ))}
        </div>
      )}
      {empty && <span className={styles.empty}>No members</span>}
    </>
  )
}

function PersonNode({ person }: { person: HierarchyNode }) {
  const navigate = useNavigate()
  const subtitle = [ROLE_LABELS[person.role], person.job_title].filter(Boolean).join(' · ')
  return (
    <button
      type="button"
      className={styles.node}
      data-role={person.role}
      onClick={() => navigate(`/people/${person.id}`)}
      title={person.teams.length ? `Workspaces: ${person.teams.join(', ')}` : 'No workspace'}
    >
      <Avatar name={person.display_name} src={person.avatar} size={32} />
      <span className={styles.nodeText}>
        <span className={styles.nodeName}>{person.display_name}</span>
        <span className={styles.nodeRole}>{subtitle}</span>
        {person.teams.length > 0 && <span className={styles.nodeTeams}>{person.teams.join(', ')}</span>}
      </span>
    </button>
  )
}
