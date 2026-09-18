import { useParams } from 'react-router-dom'

import { IssueView } from './IssueView'

export function IssueDetailPage() {
  const { issueKey } = useParams<{ issueKey: string }>()
  if (!issueKey) return null
  return <IssueView issueKey={issueKey} />
}
