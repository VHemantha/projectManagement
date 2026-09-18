interface DocNode {
  type?: string
  text?: string
  content?: DocNode[]
}

export function extractPlainText(doc: Record<string, unknown> | null | undefined, maxLength = 200): string {
  if (!doc) return ''
  const parts: string[] = []
  const walk = (node: DocNode) => {
    if (node.text) parts.push(node.text)
    node.content?.forEach(walk)
  }
  walk(doc as DocNode)
  const text = parts.join(' ').trim()
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text
}
