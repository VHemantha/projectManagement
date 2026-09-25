import { ArrowDown, ArrowUp, Columns3, RotateCcw } from 'lucide-react'

import styles from './ColumnsMenu.module.css'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/design-system'

export interface ColumnsMenuItem {
  id: string
  label: string
  visible: boolean
  /** Some columns (e.g. the row key) can't be hidden. */
  required?: boolean
}

/** "Columns" menu shared by every customisable table: tick columns on/off, move them up/down,
 * reset to the table's default layout. Items are listed in their current display order. */
export function ColumnsMenu({
  items,
  onToggle,
  onMove,
  onReset,
  isCustomized,
}: {
  items: ColumnsMenuItem[]
  onToggle: (id: string) => void
  onMove: (id: string, direction: -1 | 1) => void
  onReset: () => void
  isCustomized: boolean
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className={styles.trigger}>
          <Columns3 size={14} /> Columns
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <div className={styles.menu}>
          <div className={styles.hint}>Show, hide and reorder columns. Saved for you.</div>
          {items.map((item, index) => (
            <div key={item.id} className={styles.row}>
              <label className={styles.label}>
                <input
                  type="checkbox"
                  checked={item.visible}
                  disabled={item.required}
                  onChange={() => onToggle(item.id)}
                />
                {item.label}
              </label>
              <button
                type="button"
                className={styles.move}
                aria-label={`Move ${item.label} up`}
                disabled={index === 0}
                onClick={() => onMove(item.id, -1)}
              >
                <ArrowUp size={12} />
              </button>
              <button
                type="button"
                className={styles.move}
                aria-label={`Move ${item.label} down`}
                disabled={index === items.length - 1}
                onClick={() => onMove(item.id, 1)}
              >
                <ArrowDown size={12} />
              </button>
            </div>
          ))}
          <button type="button" className={styles.reset} disabled={!isCustomized} onClick={onReset}>
            <RotateCcw size={12} /> Reset to default
          </button>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
