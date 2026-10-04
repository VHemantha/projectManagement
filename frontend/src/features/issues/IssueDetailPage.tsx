import { Navigate, useParams } from 'react-router-dom'

import { IssueView } from './IssueView'
import { useIssue } from '@/api/issues'

export function IssueDetailPage() {
  const { key, issueKey } = useParams<{ key: string; issueKey: string }>()
  const { data: issue } = useIssue(issueKey)
  if (!issueKey) return null
  // An old key (the project was renamed) or different letter case: show the current URL.
  if (issue && (issue.key !== issueKey || issue.project !== key)) {
    return <Navigate replace to={`/projects/${issue.project}/issues/${issue.key}`} />
  }
  return <IssueView issueKey={issueKey} />
}
