import { create } from 'zustand'

interface PresenceState {
  onlineUserIds: Set<number>
  setSnapshot: (ids: number[]) => void
  setOnline: (id: number) => void
  setOffline: (id: number) => void
}

export const usePresenceStore = create<PresenceState>()((set) => ({
  onlineUserIds: new Set(),
  setSnapshot: (ids) => set({ onlineUserIds: new Set(ids) }),
  setOnline: (id) => set((s) => ({ onlineUserIds: new Set(s.onlineUserIds).add(id) })),
  setOffline: (id) =>
    set((s) => {
      const next = new Set(s.onlineUserIds)
      next.delete(id)
      return { onlineUserIds: next }
    }),
}))
