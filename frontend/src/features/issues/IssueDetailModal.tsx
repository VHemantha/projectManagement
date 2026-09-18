import * as RadixDialog from '@radix-ui/react-dialog'

import dialogStyles from '@/design-system/Dialog.module.css'
import { IssueView } from './IssueView'
import { useUiStore } from '@/store/uiStore'

export function IssueDetailModal() {
  const issueModalKey = useUiStore((s) => s.issueModalKey)
  const closeIssueModal = useUiStore((s) => s.closeIssueModal)

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
              <IssueView issueKey={issueModalKey} isModal onClose={closeIssueModal} />
            </div>
          </RadixDialog.Content>
        </RadixDialog.Portal>
      )}
    </RadixDialog.Root>
  )
}
