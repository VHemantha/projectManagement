import { format, parseISO } from 'date-fns'
import { FileText } from 'lucide-react'

import styles from './Coordinator.module.css'
import { openCeoReport, useCeoReports } from '@/api/coordinator'
import { Button, Skeleton } from '@/design-system'

/** The PDF reports the CEO asked the Practice Manager AI for in Messages (AFIT, 21 Nov 2026). CEO only. */
export function ReportsTab() {
  const { data, isLoading, isError } = useCeoReports()
  if (isLoading) return <Skeleton height={80} />
  if (isError || !data) return <p className={styles.error}>The reports could not be loaded.</p>
  return (
    <section aria-label="Reports">
      <p className={styles.muted}>
        Ask the Practice Manager AI for a report in Messages (e.g. “give me a report on the team&apos;s hours this month”). It answers with a PDF of
        charts and tables, worked out from the records; every report is kept here.
      </p>
      {data.reports.length === 0 ? (
        <p className={styles.muted}>No reports yet.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr><th>Report</th><th>You asked</th><th>When</th><th /></tr>
          </thead>
          <tbody>
            {data.reports.map((r) => (
              <tr key={r.id}>
                <th scope="row">{r.title}</th>
                <td>{r.request}</td>
                <td>{format(parseISO(r.created_at), 'dd MMM yyyy, HH:mm')}</td>
                <td>
                  <Button size="sm" variant="subtle" onClick={() => openCeoReport(r.id)}>
                    <FileText size={13} /> Open PDF
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
