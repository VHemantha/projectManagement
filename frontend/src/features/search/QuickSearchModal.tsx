import * as RadixDialog from '@radix-ui/react-dialog'
import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import styles from './QuickSearchModal.module.css'
import { useQuickSearch } from '@/api/search'
import { IssueKey, IssueTypeIcon } from '@/design-system'
import { useUiStore } from '@/store/uiStore'

export function QuickSearchModal() {
  const open = useUiStore((s) => s.quickSearchOpen)
  const toggleQuickSearch = useUiStore((s) => s.toggleQuickSearch)
  const closeQuickSearch = useUiStore((s) => s.closeQuickSearch)
  const openIssueModal = useUiStore((s) => s.openIssueModal)
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const { data, isFetching } = useQuickSearch(query)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        toggleQuickSearch()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [toggleQuickSearch])

  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  const hasResults = (data?.issues.length ?? 0) > 0 || (data?.projects.length ?? 0) > 0

  return (
    <RadixDialog.Root open={open} onOpenChange={(next) => !next && closeQuickSearch()}>
      {open && (
        <RadixDialog.Portal>
          <RadixDialog.Overlay className={styles.overlay} />
          <RadixDialog.Content className={styles.content} aria-describedby={undefined}>
            <RadixDialog.Title style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }}>
              Quick search
            </RadixDialog.Title>
            <div className={styles.inputRow}>
              <Search size={16} color="var(--tf-text-subtle)" />
              <input
                className={styles.input}
                autoFocus
                placeholder="Search issues and projects…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className={styles.results}>
              {query.trim().length === 0 && (
                <div className={styles.empty}>Type to search issues by key or summary, or a project.</div>
              )}
              {query.trim().length > 0 && !isFetching && !hasResults && (
                <div className={styles.empty}>No results for &ldquo;{query}&rdquo;.</div>
              )}
              {(data?.issues.length ?? 0) > 0 && (
                <>
                  <div className={styles.sectionLabel}>Issues</div>
                  {data!.issues.map((issue) => (
                    <div
                      key={issue.id}
                      className={styles.row}
                      onClick={() => {
                        closeQuickSearch()
                        openIssueModal(issue.key)
                      }}
                    >
                      <IssueTypeIcon typeName={issue.issue_type.name} size={14} />
                      <IssueKey value={issue.key} />
                      <span>{issue.summary}</span>
                    </div>
                  ))}
                </>
              )}
              {(data?.projects.length ?? 0) > 0 && (
                <>
                  <div className={styles.sectionLabel}>Projects</div>
                  {data!.projects.map((project) => (
                    <div
                      key={project.id}
                      className={styles.row}
                      onClick={() => {
                        closeQuickSearch()
                        navigate(`/projects/${project.key}`)
                      }}
                    >
                      <span
                        style={{
                          width: 18,
                          height: 18,
                          borderRadius: 3,
                          background: project.avatar_color,
                          display: 'inline-flex',
                          flexShrink: 0,
                        }}
                      />
                      {project.name} <span style={{ color: 'var(--tf-text-subtle)' }}>({project.key})</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </RadixDialog.Content>
        </RadixDialog.Portal>
      )}
    </RadixDialog.Root>
  )
}
