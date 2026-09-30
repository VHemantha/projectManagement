import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type PanelId = 'projectsTree' | 'projectNav' | 'jobFilters'

interface SidebarState {
  /** Which secondary sidebars are expanded. All start collapsed to an icon rail. */
  open: Record<PanelId, boolean>
  setOpen: (panel: PanelId, open: boolean) => void
  toggle: (panel: PanelId) => void
}

/** Open/closed state of the secondary sidebars (Projects tree, project menu, job filters),
 * remembered per browser like the rest of the UI chrome. */
export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      open: { projectsTree: false, projectNav: false, jobFilters: false },
      setOpen: (panel, open) => set((s) => ({ open: { ...s.open, [panel]: open } })),
      toggle: (panel) => set((s) => ({ open: { ...s.open, [panel]: !s.open[panel] } })),
    }),
    { name: 'trackflow-sidebars' },
  ),
)

export function usePanel(panel: PanelId) {
  const open = useSidebarStore((s) => s.open[panel])
  const setOpen = useSidebarStore((s) => s.setOpen)
  const toggle = useSidebarStore((s) => s.toggle)
  return { open, setOpen: (value: boolean) => setOpen(panel, value), toggle: () => toggle(panel) }
}
