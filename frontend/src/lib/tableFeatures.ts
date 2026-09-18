import {
  columnResizingFeature,
  columnSizingFeature,
  columnVisibilityFeature,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_alphanumeric,
  tableFeatures,
} from '@tanstack/react-table'

// Feature set for simple, static tables (e.g. the Projects list): sorting only.
export const tfTableFeatures = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric },
})

// Feature set for the reusable <IssueTable>: sorting + resizable + hideable
// columns. "Group by" is handled by hand (partitioning rows into labeled
// sections) rather than TanStack's grouped-row-model, which is built for
// collapsible pivot-style trees rather than a flat, section-headed list.
export const issueTableFeatures = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { alphanumeric: sortFn_alphanumeric },
  columnSizingFeature,
  columnResizingFeature,
  columnVisibilityFeature,
})
