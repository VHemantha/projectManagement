import { format, subDays } from 'date-fns'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useNavigate } from 'react-router-dom'

import { useIssues } from '@/api/issues'
import { useTimeEntries } from '@/api/timesheets'
import type { TeamDetail } from '@/api/types'
import { Avatar } from '@/design-system'
import { IssueTable } from '@/features/tables/IssueTable'
import type { GroupByOption } from '@/features/tables/IssueTable'

const PERIOD_DAYS = 30

export function TeamIssuesTab({ team }: { team: TeamDetail }) {
  const memberIds = useMemo(() => team.memberships.map((m) => m.user.id), [team])
  const [groupBy, setGroupBy] = useState<GroupByOption>('project')
  const [sortKey, setSortKey] = useState<'issues' | 'hours'>('hours')
  const [sortDesc, setSortDesc] = useState(true)
  const navigate = useNavigate()

  const { data: issuesPage, isLoading } = useIssues(
    { assignee_in: memberIds.join(','), page_size: 300, ordering: 'rank' },
    memberIds.length > 0,
  )
  const issues = issuesPage?.results ?? []

  const dateFrom = format(subDays(new Date(), PERIOD_DAYS), 'yyyy-MM-dd')
  const { data: entries } = useTimeEntries(
    { user_in: memberIds.join(','), date_from: dateFrom, page_size: 1000 },
    memberIds.length > 0,
  )

  const rows = useMemo(
    () =>
      team.memberships.map((m) => {
        const hours =
          (entries ?? []).filter((e) => e.user.id === m.user.id).reduce((sum, e) => sum + e.duration_seconds, 0) /
          3600
        const issueCount = issues.filter((i) => i.assignee?.id === m.user.id).length
        return { user: m.user, hours, issues: issueCount }
      }),
    [team, entries, issues],
  )

  const sortedRows = [...rows].sort((a, b) => {
    const diff = a[sortKey] - b[sortKey]
    return sortDesc ? -diff : diff
  })

  const workload = rows.map((r) => ({ name: r.user.display_name.split(' ')[0], issues: r.issues }))

  const toggleSort = (key: 'issues' | 'hours') => {
    if (key === sortKey) setSortDesc((d) => !d)
    else {
      setSortKey(key)
      setSortDesc(true)
    }
  }

  return (
    <div style={{ padding: '0 24px 24px' }}>
      <div style={{ height: 180, marginBottom: 24, background: 'var(--tf-surface)', border: '1px solid var(--tf-border)', borderRadius: 8, padding: 12 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={workload}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--tf-border)" />
            <XAxis dataKey="name" fontSize={12} stroke="var(--tf-text-subtle)" />
            <YAxis allowDecimals={false} fontSize={12} stroke="var(--tf-text-subtle)" />
            <Tooltip />
            <Bar dataKey="issues" fill="var(--tf-blue)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, background: 'var(--tf-surface)', border: '1px solid var(--tf-border)', borderRadius: 8, overflow: 'hidden' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', padding: '8px 12px', fontSize: 11, color: 'var(--tf-text-subtle)', textTransform: 'uppercase', borderBottom: '1px solid var(--tf-border)' }}>
              Member
            </th>
            <th
              style={{ textAlign: 'right', padding: '8px 12px', fontSize: 11, color: 'var(--tf-text-subtle)', textTransform: 'uppercase', borderBottom: '1px solid var(--tf-border)', cursor: 'pointer' }}
              onClick={() => toggleSort('issues')}
            >
              Issues {sortKey === 'issues' && (sortDesc ? <ArrowDown size={10} /> : <ArrowUp size={10} />)}
            </th>
            <th
              style={{ textAlign: 'right', padding: '8px 12px', fontSize: 11, color: 'var(--tf-text-subtle)', textTransform: 'uppercase', borderBottom: '1px solid var(--tf-border)', cursor: 'pointer' }}
              onClick={() => toggleSort('hours')}
            >
              Hours logged (30d) {sortKey === 'hours' && (sortDesc ? <ArrowDown size={10} /> : <ArrowUp size={10} />)}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr key={row.user.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/people/${row.user.id}`)}>
              <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--tf-border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Avatar name={row.user.display_name} src={row.user.avatar} size={24} userId={row.user.id} interactive />
                {row.user.display_name}
              </td>
              <td style={{ padding: '8px 12px', textAlign: 'right', borderBottom: '1px solid var(--tf-border)' }}>{row.issues}</td>
              <td style={{ padding: '8px 12px', textAlign: 'right', borderBottom: '1px solid var(--tf-border)', fontWeight: 600 }}>
                {row.hours.toFixed(1)}h
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 24 }}>
        <IssueTable
          issues={issues}
          isLoading={isLoading}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
          availableGroupBy={['none', 'project', 'status', 'assignee']}
          showProjectColumn
          emptyMessage="No issues assigned to this team's members."
        />
      </div>
    </div>
  )
}
