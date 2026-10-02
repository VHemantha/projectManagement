import { Trash2 } from 'lucide-react'

import styles from './FiltersPage.module.css'
import { useDeleteFilter, useFilters, useRenameFilter } from '@/api/search'
import { Button, InlineEdit } from '@/design-system'
import { useAuthStore } from '@/store/authStore'

export function FiltersPage() {
  const { data: filters, isLoading } = useFilters()
  const deleteFilter = useDeleteFilter()
  const renameFilter = useRenameFilter()
  const currentUser = useAuthStore((s) => s.user)

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Filters</h1>
      {isLoading ? (
        <div>Loading…</div>
      ) : !filters || filters.length === 0 ? (
        <div className={styles.empty}>
          No saved filters yet. Save one from the filter panel on a workspace&apos;s Jobs tab.
        </div>
      ) : (
        filters.map((f) => (
          <div key={f.id} className={styles.row}>
            <div>
              <InlineEdit
                as="div"
                className={styles.name}
                value={f.name}
                label="Filter name"
                canEdit={f.owner === currentUser?.id}
                onSave={(name) => renameFilter.mutateAsync({ id: f.id, name })}
              />
              <div className={styles.meta}>by {f.owner_name}</div>
            </div>
            <span className={styles.visibility}>{f.is_public ? 'Shared' : 'Private'}</span>
            {f.owner === currentUser?.id && (
              <Button variant="subtle" size="sm" iconOnly onClick={() => deleteFilter.mutate(f.id)} aria-label="Delete filter">
                <Trash2 size={14} />
              </Button>
            )}
          </div>
        ))
      )}
    </div>
  )
}
