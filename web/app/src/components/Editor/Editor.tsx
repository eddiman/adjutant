import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Highlight from '@tiptap/extension-highlight';
import Placeholder from '@tiptap/extension-placeholder';
import Image from '@tiptap/extension-image';
import { Extension } from '@tiptap/core';
import { Markdown } from 'tiptap-markdown';
import { useEffect, useCallback, useRef } from 'react';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import styles from './Editor.module.css';

// Use relative URLs - Vite proxy handles /api routes

// Plugin key for image paste handling
const imagePastePluginKey = new PluginKey('imagePaste');

// Module-level KB tracker — the ProseMirror plugin reads this when uploading images
let currentEditorKb: string | undefined;

interface EditorProps {
  content: string;
  onChange: (content: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  kb?: string;
}

// Upload an image file and return the URL
async function uploadImage(file: File, kb?: string): Promise<string | null> {
  try {
    const formData = new FormData();
    formData.append('image', file);
    if (kb) formData.append('kb', kb);

    const response = await fetch(`/api/assets/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      console.error('Failed to upload image:', response.statusText);
      return null;
    }

    const data = await response.json();
    // Return the WebP URL for the uploaded image
    return data.webpUrl;
  } catch (error) {
    console.error('Error uploading image:', error);
    return null;
  }
}

// Custom extension to handle image paste/drop
const ImagePasteExtension = Extension.create({
  name: 'imagePaste',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: imagePastePluginKey,
        props: {
          handlePaste(view, event) {
            const items = event.clipboardData?.items;
            if (!items) return false;

            for (const item of items) {
              if (item.type.startsWith('image/')) {
                event.preventDefault();
                const file = item.getAsFile();
                if (file) {
                  // Upload the image and insert it
                  uploadImage(file, currentEditorKb).then(url => {
                    if (url) {
                      const { state, dispatch } = view;
                      const node = state.schema.nodes.image.create({ src: url });
                      const tr = state.tr.replaceSelectionWith(node);
                      dispatch(tr);
                    }
                  });
                }
                return true;
              }
            }
            return false;
          },
          handleDrop(view, event) {
            const files = event.dataTransfer?.files;
            if (!files || files.length === 0) return false;

            for (const file of files) {
              if (file.type.startsWith('image/')) {
                event.preventDefault();
                // Upload the image and insert it at drop position
                uploadImage(file, currentEditorKb).then(url => {
                  if (url) {
                    const coordinates = view.posAtCoords({
                      left: event.clientX,
                      top: event.clientY,
                    });
                    if (coordinates) {
                      const { state, dispatch } = view;
                      const node = state.schema.nodes.image.create({ src: url });
                      const tr = state.tr.insert(coordinates.pos, node);
                      dispatch(tr);
                    }
                  }
                });
                return true;
              }
            }
            return false;
          },
        },
      }),
    ];
  },
});

export function Editor({ content, onChange, placeholder = 'Start writing...', autoFocus = false, kb }: EditorProps) {
  // Update module-level KB for the ProseMirror image paste plugin
  currentEditorKb = kb;

  // Track internal content to avoid re-setting from prop when we just made the change
  const lastContentRef = useRef<string>(content);
  // Track if we've completed initial mount to avoid state updates during render
  const isMountedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Highlight.configure({
        multicolor: false,
      }),
      Placeholder.configure({
        placeholder,
      }),
      Image.configure({
        inline: false,
        allowBase64: false,
        HTMLAttributes: {
          class: 'editor-image',
        },
      }),
      Markdown.configure({
        html: false,
        transformPastedText: true,
        transformCopiedText: true,
      }),
      ImagePasteExtension,
    ],
    content,
    autofocus: false,
    editorProps: {
      attributes: {
        class: styles['editor-content'],
      },
    },
    onUpdate: ({ editor }) => {
      // Skip updates before component is mounted or if editor is destroyed
      if (!isMountedRef.current || !editor || editor.isDestroyed) return;
      
      // Get markdown content instead of HTML
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const markdown = (editor.storage as any).markdown.getMarkdown() as string;
      lastContentRef.current = markdown;
      onChange(markdown);
    },
  });

  // Update content when prop changes (e.g., loading a different note)
  useEffect(() => {
    if (editor && content !== lastContentRef.current) {
      lastContentRef.current = content;
      editor.commands.setContent(content);
      // Scroll to top when loading new content
      const timer = setTimeout(() => {
        if (editor && !editor.isDestroyed) {
          editor.commands.focus('start');
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [editor, content]);

  // Handle autoFocus by focusing at start when editor is ready
  useEffect(() => {
    if (autoFocus && editor) {
      const timer = setTimeout(() => {
        if (editor && !editor.isDestroyed) {
          editor.commands.focus('start');
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [autoFocus, editor]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Allow Escape and Cmd/Ctrl+S to propagate for parent handling
    if (e.key === 'Escape') return;
    if ((e.metaKey || e.ctrlKey) && e.key === 's') return;
    
    // Prevent canvas shortcuts while editing
    e.stopPropagation();
  }, []);

  // Toolbar button for inserting image via file picker
  const handleImageButtonClick = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file && editor) {
        const url = await uploadImage(file, kb);
        if (url) {
          editor.chain().focus().setImage({ src: url }).run();
        }
      }
    };
    input.click();
  }, [editor]);

  if (!editor) {
    return <div className={styles['editor-loading']}>Loading editor...</div>;
  }

  return (
    <div className={styles['editor-wrapper']} onKeyDown={handleKeyDown}>
      <div className={styles['editor-toolbar']}>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
          className={editor.isActive('heading', { level: 1 }) ? styles['active'] : ''}
          title="Heading 1"
        >
          H1
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          className={editor.isActive('heading', { level: 2 }) ? styles['active'] : ''}
          title="Heading 2"
        >
          H2
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
          className={editor.isActive('heading', { level: 3 }) ? styles['active'] : ''}
          title="Heading 3"
        >
          H3
        </button>
        <span className={styles['toolbar-divider']} />
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleBold().run()}
          className={editor.isActive('bold') ? styles['active'] : ''}
          title="Bold"
        >
          B
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleItalic().run()}
          className={editor.isActive('italic') ? styles['active'] : ''}
          title="Italic"
        >
          I
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleHighlight().run()}
          className={editor.isActive('highlight') ? styles['active'] : ''}
          title="Highlight"
        >
          HL
        </button>
        <span className={styles['toolbar-divider']} />
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          className={editor.isActive('bulletList') ? styles['active'] : ''}
          title="Bullet List"
        >
          List
        </button>
        <button
          type="button"
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          className={editor.isActive('orderedList') ? styles['active'] : ''}
          title="Numbered List"
        >
          1.
        </button>
        <span className={styles['toolbar-divider']} />
        <button
          type="button"
          onClick={handleImageButtonClick}
          title="Insert Image"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </button>
      </div>
      <EditorContent editor={editor} />
    </div>
  );
}
