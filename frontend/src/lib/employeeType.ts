/** Employee types (AFIT, 16 Nov 2026): Standard, Team Lead (an organisation admin: what was
 * "Admin") and the CEO (what was "Worker" is Standard). One wording everywhere. */
export type EmployeeType = 'ceo' | 'team_lead' | 'standard'

export const EMPLOYEE_TYPE_LABEL: Record<EmployeeType, string> = { ceo: 'CEO', team_lead: 'Team Lead', standard: 'Standard' }

export function employeeType(user: { role?: string; is_staff?: boolean } | null | undefined): EmployeeType {
  if (user?.role === 'ceo') return 'ceo'
  return user?.is_staff ? 'team_lead' : 'standard'
}

export function employeeTypeLabel(user: { role?: string; is_staff?: boolean } | null | undefined): string {
  return EMPLOYEE_TYPE_LABEL[employeeType(user)]
}
