import styles from './Avatar.module.css'

const PALETTE = [
  '#0C66E4',
  '#36B37E',
  '#8777D9',
  '#E5493A',
  '#00B8D9',
  '#FF8B00',
  '#6554C0',
  '#1F845A',
]

function colorFor(seed: string) {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = seed.charCodeAt(i) + ((hash << 5) - hash)
  return PALETTE[Math.abs(hash) % PALETTE.length]
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

interface AvatarProps {
  name: string
  src?: string | null
  size?: number
}

export function Avatar({ name, src, size = 24 }: AvatarProps) {
  const style = {
    width: size,
    height: size,
    fontSize: Math.max(10, size * 0.42),
    background: src ? undefined : colorFor(name || '?'),
  }
  return (
    <span className={styles.avatar} style={style} title={name}>
      {src ? <img className={styles.img} src={src} alt={name} /> : initials(name || '?')}
    </span>
  )
}
