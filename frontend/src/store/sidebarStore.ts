import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type PanelId = 'projectsTree' | 'jobFilters' | 'workspaceDashboard'

interface SidebarState {
  /** Which secondary sidebars are expanded. Most start collapsed to an icon rail; the workspace
   * dashboard starts open. */
  open: Record<PanelId, boolean>
  setOpen: (panel: PanelId, open: boolean) => void
  toggle: (panel: PanelId) => void
}

/** Open/closed state of the secondary panels (Workspaces tree, job filters, workspace dashboard),
 * remembered per browser like the rest of the UI chrome. */
export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      open: { projectsTree: false, jobFilters: false, workspaceDashboard: true },
      setOpen: (panel, open) => set((s) => ({ open: { ...s.open, [panel]: open } })),
      toggle: (panel) => set((s) => ({ open: { ...s.open, [panel]: !s.open[panel] } })),
    }),
    {
      name: 'trackflow-sidebars',
      // Panels added since a browser saved its state take their defaults.
      merge: (persisted, current) => {
        const saved = (persisted as Partial<SidebarState> | undefined)?.open ?? {}
        return { ...current, open: { ...current.open, ...saved } }
      },
    },
  ),
)

export function usePanel(panel: PanelId) {
  const open = useSidebarStore((s) => s.open[panel])
  const setOpen = useSidebarStore((s) => s.setOpen)
  const toggle = useSidebarStore((s) => s.toggle)
  return { open, setOpen: (value: boolean) => setOpen(panel, value), toggle: () => toggle(panel) }
}
