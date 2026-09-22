import { useParams } from 'react-router-dom'

import styles from './TeamBoardPage.module.css'
import { useTeam } from '@/api/teams'
import { TeamBoard } from './TeamBoard'
import { TeamGoalsTab } from './TeamGoalsTab'
import { TeamIssuesTab } from './TeamIssuesTab'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'

export function TeamDetailPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const { data: team } = useTeam(teamId)

  if (!team) return null

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div className={styles.header}>
        <span className={styles.avatar} style={{ background: team.avatar_color }}>
          {team.name.slice(0, 2).toUpperCase()}
        </span>
        <div>
          <div className={styles.title}>{team.name}</div>
          <div className={styles.subtitle}>{team.memberships.length} members</div>
        </div>
      </div>

      <Tabs defaultValue="board" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ padding: '0 24px' }}>
          <TabsList>
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="issues">Issues</TabsTrigger>
            <TabsTrigger value="goals">Team Goals</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="board" style={{ flex: 1, minHeight: 0 }}>
          <TeamBoard team={team} />
        </TabsContent>
        <TabsContent value="issues">
          <TeamIssuesTab team={team} />
        </TabsContent>
        <TabsContent value="goals">
          <TeamGoalsTab team={team} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
