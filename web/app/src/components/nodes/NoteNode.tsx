import { memo, useRef, useEffect, useCallback } from 'react';
import { Handle, Position } from '@xyflow/react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Highlight from '@tiptap/extension-highlight';
import Image from '@tiptap/extension-image';
import { Markdown } from 'tiptap-markdown';
import styles from './NoteNode.module.css';

export interface OriginRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface NoteNodeData {
  filename: string;
  path: string;
  kb: string;
  title: string;
  content: string;
  tags: string[];
  onOpen: (notePath: string, originRect: OriginRect) => void;
  isPanMode?: boolean;
  isHighlighted?: boolean;
  [key: string]: unknown;
}

// Read-only TipTap editor for rendering markdown content
function ReadOnlyContent({ content }: { content: string }) {
  const lastContentRef = useRef<string>(content);
  
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      Highlight.configure({ multicolor: false }),
      Image.configure({
        inline: false,
        allowBase64: false,
        HTMLAttributes: {
          class: 'note-preview-image',
        },
      }),
      Markdown.configure({
        html: false,
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content,
    editable: false,
    editorProps: {
      attributes: {
        class: 'note-card-content',
      },
    },
  });

  useEffect(() => {
    if (editor && content !== lastContentRef.current) {
      lastContentRef.current = content;
      editor.commands.setContent(content);
    }
  }, [editor, content]);

  if (!editor) return null;

  return <EditorContent editor={editor} />;
}

function NoteNodeComponent({ data }: { data: NoteNodeData }) {
  const nodeRef = useRef<HTMLDivElement>(null);

  const openNote = useCallback(() => {
    if (nodeRef.current) {
      const rect = nodeRef.current.getBoundingClientRect();
      data.onOpen(data.path, {
        x: rect.left,
        y: rect.top,
        width: rect.width,
        height: rect.height,
      });
    } else {
      data.onOpen(data.path, { x: 0, y: 0, width: 200, height: 283 });
    }
  }, [data]);

  const handleDoubleClick = useCallback(() => {
    if (data.isPanMode) return;
    openNote();
  }, [openNote, data.isPanMode]);

  return (
    <div 
      ref={nodeRef}
      className={`${styles['note-node']}${data.isHighlighted ? ` ${styles.highlighted}` : ''}`}
      onDoubleClick={handleDoubleClick}
    >
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      
      <div className={styles['note-node-paper']}>
        <h1 className={styles['note-node-title']}>{data.title || 'Untitled'}</h1>
        <ReadOnlyContent content={data.content || ''} />
        <div className={styles['note-node-fade']} />
      </div>
      
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </div>
  );
}

export const NoteNode = memo(NoteNodeComponent);
