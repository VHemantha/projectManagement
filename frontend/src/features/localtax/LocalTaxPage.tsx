import { ArrowLeft, Building2 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { ComputationStage } from './ComputationStage'
import { FinancialStatementsStage } from './FinancialStatementsStage'
import styles from './LocalTax.module.css'
import { type ClientInfoSection, QuestionnaireStage } from './QuestionnaireStage'
import { ReturnStage } from './ReturnStage'
import { Stepper } from './Shared'
import { extractErrorMessage } from '@/api/errors'
import { type StageKey, STAGES, useLocalTax } from '@/api/localTax'
import { Button, Skeleton } from '@/design-system'

/** Where the workflow is: the stage, and the Client Info section to open on (e.g. Supporting Documents). */
export interface WorkflowPlace { stage: StageKey; section?: ClientInfoSection }

/** The Local Tax workflow (Team 3 > Local cards): the client bar, the four-stage stepper and the stage. "Back to AI
 * Workflow" returns to the four-box overview; each stage has Back and Next to the stage before and after. */
export function LocalTaxWorkflow({ taskKey, place, onPlace, onClose }: {
  taskKey: string; place: WorkflowPlace; onPlace: (p: WorkflowPlace) => void; onClose: () => void
}) {
  const { data, isLoading, isError, error } = useLocalTax(taskKey)
  if (isLoading) return <div className={styles.page}><Skeleton height={200} /></div>
  if (isError || !data) {
    return <div className={styles.page}><p className={styles.error}>{extractErrorMessage(error, 'The Local Tax workflow could not be opened.')}</p></div>
  }
  const e = data.engagement
  const stage = place.stage
  const i = STAGES.findIndex((x) => x.key === stage)
  const go = (s: StageKey, section?: ClientInfoSection) => {
    onPlace({ stage: s, section })
    document.querySelector('[data-localtax-top]')?.scrollIntoView?.({ block: 'start' })
  }
  const next = () => go(STAGES[Math.min(i + 1, STAGES.length - 1)].key)
  const back = i > 0 ? () => go(STAGES[i - 1].key) : undefined
  return (
    <div className={styles.page} data-localtax-top>
      <div className={styles.clientBar}>
        <Button variant="secondary" size="sm" onClick={onClose}><ArrowLeft size={14} /> Back to AI Workflow</Button>
        <div>
          <h1 className={styles.clientName}>AI Workflow – Local Tax Engagement</h1>
          <p className={styles.clientMeta}>Sri Lankan Accounting, Financial Reporting and Income Tax Preparation</p>
        </div>
        <span className={styles.spacer} />
        <Building2 size={20} aria-hidden="true" />
        <div>
          <p className={styles.clientName}>{e.legal_name || taskKey}</p>
          <p className={styles.clientMeta}>TIN: {e.tin || '—'} | YA: {e.year_of_assessment}</p>
        </div>
      </div>
      <Stepper state={data} current={stage} onPick={(s) => go(s)} />
      {stage === 'questionnaire' && <QuestionnaireStage key={`q-${e.id}-${place.section ?? ''}`} taskKey={taskKey} state={data} onNext={next} section={place.section} />}
      {stage === 'fs' && <FinancialStatementsStage taskKey={taskKey} state={data} onNext={next} onBack={back} onDocuments={() => go('questionnaire', 'documents')} />}
      {stage === 'computation' && <ComputationStage taskKey={taskKey} state={data} onNext={next} onBack={back} onQuestionnaire={() => go('questionnaire')} />}
      {stage === 'return' && <ReturnStage taskKey={taskKey} state={data} onBack={back} />}
    </div>
  )
}

/** /local-tax/<task>?stage=…: the same workflow on its own page (a link to it opens here). */
export function LocalTaxPage() {
  const { issueKey = '' } = useParams<{ issueKey: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [section, setSection] = useState<ClientInfoSection | undefined>(undefined)
  const stage = (STAGES.some((s) => s.key === params.get('stage')) ? params.get('stage') : 'questionnaire') as StageKey
  return (
    <LocalTaxWorkflow taskKey={issueKey} place={{ stage, section }}
      onPlace={(p) => { setSection(p.section); setParams({ stage: p.stage }) }}
      onClose={() => navigate(`/projects/${issueKey.split('-')[0]}/issues/${issueKey}`)} />
  )
}
