import { type InputHTMLAttributes, forwardRef } from 'react'

import styles from './Input.module.css'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, id, className, ...props },
  ref,
) {
  const inputEl = (
    <input ref={ref} id={id} className={[styles.input, className].filter(Boolean).join(' ')} {...props} />
  )
  if (!label) return inputEl
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      {inputEl}
      {error && <span className={styles.error}>{error}</span>}
    </div>
  )
})
