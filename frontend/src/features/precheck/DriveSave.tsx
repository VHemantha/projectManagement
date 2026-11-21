import { format, parseISO } from 'date-fns'
import { ExternalLink, HardDriveUpload } from 'lucide-react'

import styles from './WpAgentPanel.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type WpRun, useSaveToDrive } from '@/api/wpAgent'
import { Button } from '@/design-system'

/** The workpaper in Google Drive (AFIT, 21 Nov 2026): saved into the task's Drive folder on request, then
 * opened from its link. Saving again replaces the file there (same link). */
export function DriveSave({ run, jobKey, disabled }: { run: WpRun; jobKey: string; disabled?: boolean }) {
  const save = useSaveToDrive(jobKey, run.run_id)
  const file = run.gst?.drive_file
  if (!run.has_workpaper) return null
  return (
    <>
      {file?.url && (
        <a className={styles.driveLink} href={file.url} target="_blank" rel="noreferrer" title={file.name}>
          <ExternalLink size={13} aria-hidden="true" /> Open in Google Drive
        </a>
      )}
      <Button type="button" variant="secondary" size="sm" onClick={() => save.mutate()} disabled={disabled || save.isPending}
        title={file ? `Saved by ${file.saved_by} on ${format(parseISO(file.saved_at), 'dd-MM-yy HH:mm')}` : "Save to the task's Drive folder"}>
        <HardDriveUpload size={14} aria-hidden="true" /> {save.isPending ? 'Saving to Drive…' : file ? 'Save to Google Drive again' : 'Save to Google Drive'}
      </Button>
      {save.isError && <span role="alert" className={styles.error}>{extractErrorMessage(save.error, 'The workpaper could not be saved to Drive.')}</span>}
    </>
  )
}
