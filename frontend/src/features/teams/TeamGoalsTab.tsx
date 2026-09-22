import { format, subDays } from 'date-fns'
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { useTeamDailyGoals, useTeamDailyGoalsRange } from '@/api/dailyGoals'
import type { TeamDetail } from '@/api/types'
import { Avatar } from '@/design-system'

const WEEK_DAYS = 7

const STATUS_LABEL: Record<string, string> = {
  planned: 'Planned',
  in_progress: 'In progress',
  achieved: 'Achieved',
  not_achieved: 'Not achieved',
  carried_over: 'Carried over',
}

const STATUS_COLOR: Record<string, string> = {
  planned: 'var(--tf-text-subtle)',
  in_progress: 'var(--tf-blue)',
  achieved: 'var(--tf-success)',
  not_achieved: 'var(--tf-danger)',
  carried_over: 'var(--tf-warning)',
}

export function TeamGoalsTab({ team }: { team: TeamDetail }) {
  const today = format(new Date(), 'yyyy-MM-dd')
  const [selectedDate, setSelectedDate] = useState(today)
  const weekStart = format(subDays(new Date(), WEEK_DAYS - 1), 'yyyy-MM-dd')

  const { data: dayGoals, isLoading, error } = useTeamDailyGoals(team.id, selectedDate)
  const { data: weekGoals } = useTeamDailyGoalsRange(team.id, weekStart, today)

  const weeklyRollup = useMemo(() => {
    return team.memberships.map((m) => {
      const mine = (weekGoals ?? []).filter((g) => g.user.id === m.user.id)
      return {
        name: m.user.display_name.split(' ')[0],
        achieved: mine.filter((g) => g.status === 'achieved').length,
        not_achieved: mine.filter((g) => g.status === 'not_achieved').length,
      }
    })
  }, [team, weekGoals])

  const goalsByMember = useMemo(() => {
    const map = new Map<number, typeof dayGoals>()
    for (const g of dayGoals ?? []) {
      const list = map.get(g.user.id) ?? []
      list.push(g)
      map.set(g.user.id, list)
    }
    return map
  }, [dayGoals])

  const isForbidden = (error as { response?: { status?: number } } | null)?.response?.status === 403

  if (isForbidden) {
    return (
      <div style={{ padding: 24, color: 'var(--tf-text-subtle)', fontSize: 13 }}>
        Only a lead of this team (or a workspace admin) can view its daily-goals rollup.
      </div>
    )
  }

  return (
    <div style={{ padding: '0 24px 24px' }}>
      <div
        style={{
          height: 200,
          marginBottom: 24,
          background: 'var(--tf-surface)',
          border: '1px solid var(--tf-border)',
          borderRadius: 8,
          padding: 12,
        }}
      >
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tf-text-subtle)', marginBottom: 4 }}>
          Achieved vs not achieved this week
        </div>
        <ResponsiveContainer width="100%" height="85%">
          <BarChart data={weeklyRollup}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--tf-border)" />
            <XAxis dataKey="name" fontSize={12} stroke="var(--tf-text-subtle)" />
            <YAxis allowDecimals={false} fontSize={12} stroke="var(--tf-text-subtle)" />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="achieved" name="Achieved" fill="var(--tf-success)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="not_achieved" name="Not achieved" fill="var(--tf-danger)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>Goals for</div>
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          style={{ fontSize: 13, height: 30, border: '1px solid var(--tf-border)', borderRadius: 4, padding: '0 8px' }}
        />
      </div>

      {isLoading ? (
        <div style={{ color: 'var(--tf-text-subtle)', fontSize: 13 }}>Loading…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {team.memberships.map((m) => {
            const goals = goalsByMember.get(m.user.id) ?? []
            return (
              <div
                key={m.id}
                style={{
                  background: 'var(--tf-surface)',
                  border: '1px solid var(--tf-border)',
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: goals.length ? 8 : 0 }}>
                  <Avatar name={m.user.display_name} src={m.user.avatar} size={24} userId={m.user.id} interactive />
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{m.user.display_name}</span>
                  {goals.length === 0 && (
                    <span style={{ fontSize: 12, color: 'var(--tf-text-subtle)', marginLeft: 8 }}>No goals set</span>
                  )}
                </div>
                {goals.map((g) => (
                  <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '4px 0 4px 32px' }}>
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: STATUS_COLOR[g.status],
                        flexShrink: 0,
                      }}
                      title={STATUS_LABEL[g.status]}
                    />
                    <span style={{ flex: 1 }}>{g.text}</span>
                    {g.status === 'not_achieved' && g.note && (
                      <span style={{ fontSize: 11, color: 'var(--tf-danger)' }}>{g.note}</span>
                    )}
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
