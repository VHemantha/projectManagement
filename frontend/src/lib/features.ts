/**
 * Build-time feature flags. Each is off unless its VITE_FEATURE_* variable is "true" (or "1"),
 * e.g. in frontend/.env.local:
 *
 *   VITE_FEATURE_SCRUM=true    # Scrum workspaces: type choice on create, sprint board, Backlog tab
 *   VITE_FEATURE_SUMMARY=true  # The workspace Summary tab
 *
 * The code behind a disabled flag is kept; switching the flag back on restores it.
 */
function flag(value: string | undefined): boolean {
  return value === 'true' || value === '1'
}

export const FEATURES = {
  scrum: flag(import.meta.env.VITE_FEATURE_SCRUM),
  summary: flag(import.meta.env.VITE_FEATURE_SUMMARY),
}

export type FeatureName = keyof typeof FEATURES

export function isEnabled(feature: FeatureName): boolean {
  return FEATURES[feature]
}
