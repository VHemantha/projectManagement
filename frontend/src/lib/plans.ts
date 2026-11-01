import { addDays, format, parseISO } from 'date-fns'

/** A morning-plan item's completion day, as the plan reads: "completion today (1 Nov 26)",
 * "completion tomorrow (2 Nov 26)", "completion Wed 4 Nov 26". */
export function completionLabel(completeBy: string, planDate: string) {
  const day = parseISO(completeBy)
  const when = format(day, 'd MMM yy')
  if (completeBy === planDate) return `completion today (${when})`
  if (completeBy === format(addDays(parseISO(planDate), 1), 'yyyy-MM-dd')) return `completion tomorrow (${when})`
  return `completion ${format(day, 'EEE')} ${when}`
}
