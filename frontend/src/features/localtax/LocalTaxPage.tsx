import { Building2, ChevronLeft } from 'lucide-react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { ComputationStage } from './ComputationStage'
import { FinancialStatementsStage } from './FinancialStatementsStage'
import styles from './LocalTax.module.css'
import { QuestionnaireStage } from './QuestionnaireStage'
import { ReturnStage } from './ReturnStage'
import { Stepper } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import { type StageKey, STAGES, useLocalTax } from '@/api/localTax'
import { Skeleton } from '@/design-system'

/** The Local Tax workflow, full screen (AFIT screens, 22 Nov 2026): /local-tax/<task>?stage=questionnaire|fs|
 * computation|return. Team 3 > Local's cards only (the API refuses any other). */
export function LocalTaxPage() {
  const { issueKey = '' } = useParams<{ issueKey: string }>()
  const [params, setParams] = useSearchParams()
  const { data, isLoading, isError, error } = useLocalTax(issueKey)
  const stage = (STAGES.some((s) => s.key === params.get('stage')) ? params.get('stage') : 'questionnaire') as StageKey
  const go = (s: StageKey) => {
    setParams({ stage: s })
    window.scrollTo?.({ top: 0 })
  }
  if (isLoading) return <div className={styles.page}><Skeleton height={200} /></div>
  if (isError || !data) {
    return <div className={styles.page}><p className={styles.error}>{extractErrorMessage(error, 'The Local Tax workflow could not be opened.')}</p></div>
  }
  const e = data.engagement
  const next = (s: StageKey) => () => go(STAGES[Math.min(STAGES.findIndex((x) => x.key === s) + 1, STAGES.length - 1)].key)
  return (
    <div className={styles.page}>
      <div className={styles.clientBar}>
        <Link to={`/projects/${issueKey.split('-')[0]}/issues/${issueKey}`} aria-label="Back to the task"><ChevronLeft size={18} /></Link>
        <div>
          <h1 className={styles.clientName} style={{ fontFamily: 'Georgia, serif', color: 'var(--tf-primary)' }}>AI Workflow – Local Tax Engagement</h1>
          <p className={styles.clientMeta}>Sri Lankan Accounting, Financial Reporting and Income Tax Preparation</p>
        </div>
        <span className={styles.spacer} />
        <Building2 size={30} aria-hidden="true" />
        <div>
          <p className={styles.clientName}>{e.legal_name || issueKey}</p>
          <p className={styles.clientMeta}>TIN: {e.tin || '—'} | YA: {e.year_of_assessment}</p>
        </div>
      </div>
      <Stepper state={data} current={stage} onPick={go} />
      {stage === 'questionnaire' && <QuestionnaireStage key={`q-${e.id}`} taskKey={issueKey} state={data} onNext={next('questionnaire')} />}
      {stage === 'fs' && <FinancialStatementsStage taskKey={issueKey} state={data} onNext={next('fs')} />}
      {stage === 'computation' && <ComputationStage taskKey={issueKey} state={data} onNext={next('computation')} onQuestionnaire={() => go('questionnaire')} />}
      {stage === 'return' && <ReturnStage taskKey={issueKey} state={data} />}
    </div>
  )
}
