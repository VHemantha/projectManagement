import { format, parseISO } from 'date-fns'

import type { LeaveRow } from '@/api/coordinator'

/** "Mon 9 Nov 2026", or "9 Nov – 10 Nov 2026" for several days. */
export const leaveDays = (r: Pick<LeaveRow, 'start_date' | 'end_date'>) =>
  r.start_date === r.end_date
    ? format(parseISO(r.start_date), 'EEE d MMM yyyy')
    : `${format(parseISO(r.start_date), 'd MMM')} – ${format(parseISO(r.end_date), 'd MMM yyyy')}`
