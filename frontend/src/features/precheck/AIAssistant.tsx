import { ClipboardCheck, Sparkles } from 'lucide-react'

import styles from './PrecheckPanel.module.css'
import { PrecheckPanel } from './PrecheckPanel'
import { ReviewPanel } from './ReviewPanel'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/design-system'

/** The AI assistant on a task card: the pre-check before the accounts are prepared, and the
 * review of the draft financial statements once they are. */
export function AIAssistant({ jobKey }: { jobKey: string }) {
  return (
    <Tabs defaultValue="precheck">
      <TabsList aria-label="AI assistant">
        <TabsTrigger value="precheck">
          <Sparkles size={13} aria-hidden="true" /> Pre-check
        </TabsTrigger>
        <TabsTrigger value="review">
          <ClipboardCheck size={13} aria-hidden="true" /> Review
        </TabsTrigger>
      </TabsList>
      <TabsContent value="precheck">
        <PrecheckPanel jobKey={jobKey} />
      </TabsContent>
      <TabsContent value="review">
        <section className={styles.panel} aria-label="AI review">
          <h2 className={styles.title}>
            <span className={styles.titleIcon} aria-hidden="true">
              <ClipboardCheck size={15} />
            </span>
            AI review of the draft financial statements
          </h2>
          <ReviewPanel jobKey={jobKey} />
        </section>
      </TabsContent>
    </Tabs>
  )
}
