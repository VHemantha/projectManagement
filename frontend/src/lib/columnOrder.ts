/** Move `id` one step within a column order, among the `movable` columns only (utility columns keep their place). */
export function moveInOrder(order: string[], id: string, direction: -1 | 1, movable: string[]): string[] {
  const listed = order.filter((c) => movable.includes(c))
  const at = listed.indexOf(id)
  const target = listed[at + direction]
  if (at === -1 || !target) return order
  const next = [...order]
  const a = next.indexOf(id)
  const b = next.indexOf(target)
  ;[next[a], next[b]] = [next[b], next[a]]
  return next
}
