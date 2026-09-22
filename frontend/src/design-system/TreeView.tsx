import { ChevronDown, ChevronRight } from 'lucide-react'
import { type ReactNode, useMemo, useState } from 'react'

import styles from './TreeView.module.css'

export interface TreeNode {
  id: string
  label: string
  type: string
  children?: TreeNode[]
  [key: string]: unknown
}

interface TreeViewProps {
  nodes: TreeNode[]
  onLeafClick: (node: TreeNode) => void
  /** Filters by label (case-insensitive) and auto-expands every branch on the path to a match,
   * rather than hiding non-matching siblings outright — keeps surrounding structure visible. */
  filterQuery?: string
  renderIcon?: (node: TreeNode) => ReactNode
  emptyMessage?: string
}

function nodeMatches(node: TreeNode, query: string): boolean {
  if (node.label.toLowerCase().includes(query)) return true
  return (node.children ?? []).some((c) => nodeMatches(c, query))
}

/** A branch whose own label or any descendant matches gets added to the expand set, then its
 * children are checked the same way — so every branch on the path to a match ends up expanded. */
function collectExpandIds(nodes: TreeNode[], query: string, acc: Set<string>) {
  for (const node of nodes) {
    if (!node.children?.length) continue
    if (nodeMatches(node, query)) {
      acc.add(node.id)
      collectExpandIds(node.children, query, acc)
    }
  }
}

/** Simple hand-rolled recursive tree — indentation + chevron-to-expand, matching this app's
 * dense information-first style rather than pulling in a third-party tree-view library. */
export function TreeView({ nodes, onLeafClick, filterQuery, renderIcon, emptyMessage = 'Nothing here yet.' }: TreeViewProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const query = filterQuery?.trim().toLowerCase() ?? ''

  const forceExpanded = useMemo(() => {
    if (!query) return new Set<string>()
    const acc = new Set<string>()
    collectExpandIds(nodes, query, acc)
    return acc
  }, [nodes, query])

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const renderNode = (node: TreeNode, depth: number): ReactNode => {
    if (query && !nodeMatches(node, query)) return null
    const hasChildren = (node.children?.length ?? 0) > 0
    const isExpanded = hasChildren && (expanded.has(node.id) || forceExpanded.has(node.id))

    return (
      <div key={node.id}>
        <div
          className={styles.row}
          style={{ paddingLeft: 8 + depth * 18 }}
          onClick={() => (hasChildren ? toggle(node.id) : onLeafClick(node))}
        >
          {hasChildren ? (
            isExpanded ? <ChevronDown size={14} className={styles.chevron} /> : <ChevronRight size={14} className={styles.chevron} />
          ) : (
            <span className={styles.chevronSpacer} />
          )}
          {renderIcon?.(node)}
          <span className={styles.label}>{node.label}</span>
        </div>
        {hasChildren && isExpanded && node.children!.map((child) => renderNode(child, depth + 1))}
      </div>
    )
  }

  if (nodes.length === 0) return <div className={styles.empty}>{emptyMessage}</div>

  return <div className={styles.tree}>{nodes.map((n) => renderNode(n, 0))}</div>
}
