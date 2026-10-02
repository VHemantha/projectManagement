import type { HierarchyTeam } from '@/api/types'

export interface TeamTree {
  team: HierarchyTeam
  children: TeamTree[]
}

/** Sub-teams nest under their parent (to any depth); teams whose parent isn't listed sit at the
 * top level. */
export function nestTeams(teams: HierarchyTeam[]): TeamTree[] {
  const ids = new Set(teams.map((t) => t.id))
  const childrenOf = new Map<number, HierarchyTeam[]>()
  for (const t of teams) {
    if (t.parent_id != null && ids.has(t.parent_id)) {
      childrenOf.set(t.parent_id, [...(childrenOf.get(t.parent_id) ?? []), t])
    }
  }
  const build = (team: HierarchyTeam, seen: Set<number>): TeamTree => ({
    team,
    children: (childrenOf.get(team.id) ?? [])
      .filter((child) => !seen.has(child.id))
      .map((child) => build(child, new Set([...seen, child.id]))),
  })
  return teams.filter((t) => t.parent_id == null || !ids.has(t.parent_id)).map((t) => build(t, new Set([t.id])))
}
