import { format, parseISO } from 'date-fns'
import { Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import styles from './TodoWidget.module.css'
import { extractErrorMessage } from '@/api/errors'
import { type TodoItem, useAddTodo, useClearDoneTodos, useDeleteTodo, useTodos, useUpdateTodo } from '@/api/todos'
import { Skeleton } from '@/design-system'

type Show = 'all' | 'work' | 'personal'

function dueLabel(due: string, today: string): { text: string; tone: string } {
  if (due < today) return { text: `Overdue · ${format(parseISO(due), 'dd-MM-yy')}`, tone: 'danger' }
  if (due === today) return { text: 'Today', tone: 'warning' }
  return { text: format(parseISO(due), 'dd-MM-yy'), tone: '' }
}

function TodoRow({ item, today }: { item: TodoItem; today: string }) {
  const update = useUpdateTodo()
  const remove = useDeleteTodo()
  const due = item.due_date && !item.done ? dueLabel(item.due_date, today) : null
  return (
    <li className={styles.item} data-done={item.done}>
      <label className={styles.tick}>
        <input type="checkbox" checked={item.done} onChange={(e) => update.mutate({ id: item.id, done: e.target.checked })} />
        <span className={styles.text}>{item.text}</span>
      </label>
      <span className={styles.kind} data-kind={item.kind}>
        {item.kind === 'personal' ? 'Personal' : 'Work'}
      </span>
      {due && (
        <span className={styles.due} data-tone={due.tone}>
          {due.text}
        </span>
      )}
      <button type="button" className={styles.remove} aria-label={`Delete: ${item.text}`} onClick={() => remove.mutate(item.id)}>
        <Trash2 size={13} aria-hidden="true" />
      </button>
    </li>
  )
}

/** My to-do list (AFIT, 5 Nov 2026): work and personal things, apart from the morning plan. Only
 * you can see it; nothing on it counts toward a rating. */
export function TodoWidget() {
  const { data, isLoading } = useTodos()
  const add = useAddTodo()
  const clear = useClearDoneTodos()
  const [text, setText] = useState('')
  const [kind, setKind] = useState<TodoItem['kind']>('work')
  const [due, setDue] = useState('')
  const [show, setShow] = useState<Show>('all')
  const today = format(new Date(), 'yyyy-MM-dd')

  const items = (data ?? []).filter((t) => show === 'all' || t.kind === show)
  const open = items.filter((t) => !t.done)
  const done = items.filter((t) => t.done)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    add.mutate(
      { text: text.trim(), kind, due_date: due || null },
      {
        onSuccess: () => {
          setText('')
          setDue('')
        },
      },
    )
  }

  return (
    <section className={styles.card} aria-label="To-do list">
      <div className={styles.header}>
        <div className={styles.title}>To-do list</div>
        <div className={styles.filters} role="group" aria-label="Show">
          {(['all', 'work', 'personal'] as const).map((s) => (
            <button key={s} type="button" aria-pressed={show === s} className={styles.filter} onClick={() => setShow(s)}>
              {s === 'all' ? 'All' : s === 'work' ? 'Work' : 'Personal'}
            </button>
          ))}
        </div>
      </div>
      <p className={styles.hint}>Only you can see this list.</p>

      <form className={styles.form} onSubmit={submit}>
        <input
          aria-label="New to-do"
          placeholder="Add a to-do…"
          value={text}
          maxLength={300}
          onChange={(e) => setText(e.target.value)}
        />
        <select aria-label="Work or personal" value={kind} onChange={(e) => setKind(e.target.value as TodoItem['kind'])}>
          <option value="work">Work</option>
          <option value="personal">Personal</option>
        </select>
        <input type="date" aria-label="Due date (optional)" value={due} onChange={(e) => setDue(e.target.value)} />
        <button type="submit" className={styles.add} disabled={!text.trim() || add.isPending}>
          Add
        </button>
      </form>
      {add.isError && (
        <p role="alert" className={styles.error}>
          {extractErrorMessage(add.error, 'The to-do could not be added. Try again.')}
        </p>
      )}

      {isLoading ? (
        <Skeleton height={60} />
      ) : open.length === 0 && done.length === 0 ? (
        <p className={styles.empty}>Nothing on your list{show === 'all' ? '' : ` (${show})`}.</p>
      ) : (
        <>
          <ul className={styles.list} aria-label="To do">
            {open.map((t) => (
              <TodoRow key={t.id} item={t} today={today} />
            ))}
          </ul>
          {done.length > 0 && (
            <>
              <div className={styles.doneHeader}>
                <span>Done ({done.length})</span>
                <button type="button" className={styles.link} onClick={() => clear.mutate()} disabled={clear.isPending}>
                  Clear done
                </button>
              </div>
              <ul className={styles.list} aria-label="Done">
                {done.map((t) => (
                  <TodoRow key={t.id} item={t} today={today} />
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  )
}
