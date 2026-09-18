import { type ButtonHTMLAttributes, forwardRef } from 'react'

import styles from './Button.module.css'

type Variant = 'primary' | 'secondary' | 'subtle' | 'danger'
type Size = 'sm' | 'md'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  iconOnly?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', iconOnly = false, className, ...props },
  ref,
) {
  const classes = [
    styles.btn,
    styles[variant],
    size === 'sm' ? styles.sm : '',
    iconOnly ? styles.iconOnly : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')
  return <button ref={ref} className={classes} {...props} />
})
