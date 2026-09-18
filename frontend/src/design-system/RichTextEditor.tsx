import Placeholder from '@tiptap/extension-placeholder'
import { EditorContent, type JSONContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Bold, Code, Italic, List, ListOrdered, Quote } from 'lucide-react'
import { useEffect } from 'react'

import styles from './RichTextEditor.module.css'

interface RichTextEditorProps {
  content: JSONContent | null
  onChange?: (json: JSONContent) => void
  editable?: boolean
  placeholder?: string
  showToolbar?: boolean
  autofocus?: boolean
}

const EMPTY_DOC: JSONContent = { type: 'doc', content: [{ type: 'paragraph' }] }

export function RichTextEditor({
  content,
  onChange,
  editable = false,
  placeholder = 'Add a description…',
  showToolbar,
  autofocus = false,
}: RichTextEditorProps) {
  const editor = useEditor({
    extensions: [StarterKit, Placeholder.configure({ placeholder })],
    content: content ?? EMPTY_DOC,
    editable,
    autofocus,
    onUpdate: ({ editor }) => onChange?.(editor.getJSON()),
    editorProps: {
      attributes: { class: styles.editor },
    },
  })

  useEffect(() => {
    if (editor) editor.setEditable(editable)
  }, [editor, editable])

  if (!editor) return null

  const toolbar = showToolbar ?? editable

  return (
    <div className={`${styles.wrap} ${editable ? styles.editable : ''}`}>
      {toolbar && (
        <div className={styles.toolbar}>
          <button
            type="button"
            className={styles.toolBtn}
            data-active={editor.isActive('bold')}
            onMouseDown={(e) => {
              e.preventDefault()
              editor.chain().focus().toggleBold().run()
            }}
            aria-label="Bold"
          >
            <Bold size={14} />
          </button>
          <button
            type="button"
            className={styles.toolBtn}
            data-active={editor.isActive('italic')}
            onMouseDown={(e) => {
              e.preventDefault()
              editor.chain().focus().toggleItalic().run()
            }}
            aria-label="Italic"
          >
            <Italic size={14} />
          </button>
          <button
            type="button"
            className={styles.toolBtn}
            data-active={editor.isActive('bulletList')}
            onMouseDown={(e) => {
              e.preventDefault()
              editor.chain().focus().toggleBulletList().run()
            }}
            aria-label="Bullet list"
          >
            <List size={14} />
          </button>
          <button
            type="button"
            className={styles.toolBtn}
            data-active={editor.isActive('orderedList')}
            onMouseDown={(e) => {
              e.preventDefault()
              editor.chain().focus().toggleOrderedList().run()
            }}
            aria-label="Numbered list"
          >
            <ListOrdered size={14} />
          </button>
          <button
            type="button"
            className={styles.toolBtn}
            data-active={editor.isActive('blockquote')}
            onMouseDown={(e) => {
              e.preventDefault()
              editor.chain().focus().toggleBlockquote().run()
            }}
            aria-label="Quote"
          >
            <Quote size={14} />
          </button>
          <button
            type="button"
            className={styles.toolBtn}
            data-active={editor.isActive('code')}
            onMouseDown={(e) => {
              e.preventDefault()
              editor.chain().focus().toggleCode().run()
            }}
            aria-label="Inline code"
          >
            <Code size={14} />
          </button>
        </div>
      )}
      <EditorContent editor={editor} />
    </div>
  )
}

export function isDocEmpty(doc: JSONContent | null | undefined) {
  if (!doc || !doc.content) return true
  return doc.content.every((node) => !node.content || node.content.length === 0)
}
