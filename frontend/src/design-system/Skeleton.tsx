import type { CSSProperties } from 'react'

import styles from './Skeleton.module.css'

interface SkeletonProps {
  width?: number | string
  height?: number | string
  style?: CSSProperties
  className?: string
}

export function Skeleton({ width = '100%', height = 14, style, className }: SkeletonProps) {
  return (
    <span
      className={`${styles.skeleton} ${className ?? ''}`}
      style={{ display: 'block', width, height, ...style }}
    />
  )
}
