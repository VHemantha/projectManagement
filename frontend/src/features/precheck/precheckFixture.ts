import type { PrecheckOutput } from '@/api/precheck'

/** A pre-check result like a real rental task's, for tests. */
export const output: PrecheckOutput = {
  decision: { state: 'requests', label: 'Requests to send', reason: '2 items are still needed before this year\'s accounts can be prepared.' },
  key_documents: [
    { role: 'questionnaire', label: 'Client questionnaire', found: true, note: '', files: [{ name: 'Client Questionnaire 2026.pdf', evidence_id: 'E1' }] },
    { role: 'last_year_fs', label: "Last year's financial statements", found: true, note: '', files: [{ name: 'FS 2025 - Signed.pdf', evidence_id: null }] },
    { role: 'last_year_workpapers', label: "Last year's workpapers", found: true, note: '', files: [{ name: 'Final TB 2025.xlsx', evidence_id: null }] },
  ],
  business_nature: {
    type: 'residential_rental', label: 'Residential rental', summary: 'One rental, 12 Kauri Street, managed by Barfoot.', fixed: false,
    reasoning: 'The questionnaire says the client owns 12 Kauri Street, let through Barfoot & Thompson.',
    sources: [{ id: 'Q3', label: 'Questionnaire: Did you own rental properties? Yes, 12 Kauri Street', evidence_id: 'E1' }],
    facts: [{ text: 'The ASB loan was refinanced in October 2025.', sources: [{ id: 'Q6', label: 'Questionnaire: Did you refinance…', evidence_id: null }] }],
  },
  requests: [
    { group: 'ASB loan', item: 'Refinancing documents', decision: 'request', reason: 'The questionnaire says the loan was refinanced; we need the old loan closing statement and the new loan details.',
      sources: [{ id: 'Q6', label: 'Questionnaire: Did you refinance…', evidence_id: null }], documents: [], flags: [] },
    { group: '12 Kauri Street', item: 'Body corporate levy invoice', decision: 'request', reason: 'Body corporate levies were 2,400 last year; the levy notice shows what they cover.',
      sources: [{ id: 'T2', label: "Last year's trial balance: Body corporate levies", evidence_id: null }], documents: [], flags: ['figure_not_in_documents'] },
  ],
  provided: [
    { group: 'ANZ 01-0123-0456789-00', item: 'Bank statements for the year', decision: 'already_provided', reason: 'The export covers the full year.',
      sources: [], documents: [{ id: 'D2', label: '01-0123-0456789-00_Transactions.xlsx', evidence_id: null }], flags: [] },
  ],
  not_needed: [
    { group: '12 Kauri Street', item: 'Home office details', decision: 'not_needed', reason: 'Barfoot manages the property.', sources: [], documents: [], flags: [] },
  ],
  preparer_notes: [{ text: 'Interest is fully deductible from 1 April 2025.', sources: [] }],
  lessons_applied: [{ id: 'L7', text: 'No home office when every property is managed.' }],
  email: { subject: 'Information still needed for your accounts for the year to 31 March 2026', body: 'Hi John,\n\nASB loan\n- Refinancing documents: …' },
  evidence: { E1: { file_name: 'Client Questionnaire 2026.pdf', location: 'line 3', quote: 'Did you own rental properties? Yes', drive_url: 'https://drive.example/cq' } },
}
