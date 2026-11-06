import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from './client'

/** One item on a person's own to-do list (AFIT, 5 Nov 2026): private to them, work or personal. */
export interface TodoItem {
  id: number
  text: string
  kind: 'work' | 'personal'
  due_date: string | null
  done: boolean
  done_at: string | null
  created_at: string
}

export type NewTodo = Pick<TodoItem, 'text'> & Partial<Pick<TodoItem, 'kind' | 'due_date'>>

const KEY = ['todos']

export function useTodos() {
  return useQuery({ queryKey: KEY, queryFn: async () => (await apiClient.get<TodoItem[]>('/todos/')).data })
}

export function useAddTodo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (item: NewTodo) => (await apiClient.post<TodoItem>('/todos/', item)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateTodo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...patch }: Partial<TodoItem> & { id: number }) =>
      (await apiClient.patch<TodoItem>(`/todos/${id}/`, patch)).data,
    // Tick at once; the list catches up when the server answers.
    onMutate: async ({ id, ...patch }) => {
      await qc.cancelQueries({ queryKey: KEY })
      qc.setQueryData<TodoItem[]>(KEY, (items) => items?.map((t) => (t.id === id ? { ...t, ...patch } : t)))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteTodo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/todos/${id}/`)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useClearDoneTodos() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => (await apiClient.post<{ removed: number }>('/todos/clear-done/')).data,
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
