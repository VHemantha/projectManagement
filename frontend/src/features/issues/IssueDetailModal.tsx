import * as RadixDialog from '@radix-ui/react-dialog'
import { ArrowLeft } from 'lucide-react'

import dialogStyles from '@/design-system/Dialog.module.css'
import { IssueView } from './IssueView'
import { useUiStore } from '@/store/uiStore'

export function IssueDetailModal() {
  const issueModalKey = useUiStore((s) => s.issueModalKey)
  const closeIssueModal = useUiStore((s) => s.closeIssueModal)
  // The task this one was opened from (e.g. the main task of a sub-task): closing goes back to it.
  const underneath = useUiStore((s) => s.issueModalStack[s.issueModalStack.length - 2] ?? null)

  return (
    <RadixDialog.Root open={!!issueModalKey} onOpenChange={(next) => !next && closeIssueModal()}>
      {issueModalKey && (
        <RadixDialog.Portal>
          <RadixDialog.Overlay className={dialogStyles.overlay} />
          <RadixDialog.Content
            className={dialogStyles.content}
            style={{ maxWidth: 1000, padding: 0 }}
            aria-describedby={undefined}
          >
            <RadixDialog.Title style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }}>
              {issueModalKey}
            </RadixDialog.Title>
            <div style={{ padding: 24 }}>
              {underneath && (
                <button
                  type="button"
                  onClick={closeIssueModal}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 4, marginBottom: 8, padding: 0, border: 'none',
                    background: 'none', color: 'var(--tf-text-link)', font: 'inherit', fontSize: 13, cursor: 'pointer',
                  }}
                >
                  <ArrowLeft size={14} aria-hidden="true" /> Back to {underneath}
                </button>
              )}
              <IssueView issueKey={issueModalKey} isModal onClose={closeIssueModal} />
            </div>
          </RadixDialog.Content>
        </RadixDialog.Portal>
      )}
    </RadixDialog.Root>
  )
}
