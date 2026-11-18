/** The last day of a month (1-12), as an ISO date: a financial year ends on the last day of its month. */
export function monthEnd(year: number, month: number): string {
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate() // day 0 of the next month = this month's last day
  return `${year}-${String(month).padStart(2, '0')}-${String(last).padStart(2, '0')}`
}
