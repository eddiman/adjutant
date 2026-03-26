import { useEffect, useState, useCallback, useRef } from 'react';
import { Editor } from '../Editor';
import { Dialog } from '../Dialog';
import { TagInput } from '../TagInput';
import type { NoteFile } from '../../types';
import type { OriginRect } from '../Canvas';
import styles from './NoteEditor.module.css';

interface NoteEditorProps {
  kb: string;
  notePath: string;
  originRect: OriginRect | null;
  initialNote?: NoteFile | null;
  sidebarOpen?: boolean;
  onClose: () => void;
  onSave: (kb: string, notePath: string, content: string, title: string, tags: string[]) => Promise<void>;
  onDelete: (kb: string, notePath: string) => Promise<void>;
  getNote: (kb: string, path: string) => Promise<NoteFile | null>;
}

const AUTOSAVE_DELAY = 1500;

export function NoteEditor({ kb, notePath, originRect, initialNote, sidebarOpen, onClose, onSave, onDelete, getNote }: NoteEditorProps) {
  const [note, setNote] = useState<NoteFile | null>(initialNote || null);
  const [loading, setLoading] = useState(!initialNote);
  const [title, setTitle] = useState(initialNote?.title || '');
  const [content, setContent] = useState(initialNote?.content || '');
  const [tags, setTags] = useState<string[]>(initialNote?.tags || []);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  const titleRef = useRef(title);
  const contentRef = useRef(content);
  const tagsRef = useRef(tags);
  const hasChangesRef = useRef(hasChanges);
  const savingRef = useRef(saving);

  useEffect(() => { titleRef.current = title; }, [title]);
  useEffect(() => { contentRef.current = content; }, [content]);
  useEffect(() => { tagsRef.current = tags; }, [tags]);
  useEffect(() => { hasChangesRef.current = hasChanges; }, [hasChanges]);
  useEffect(() => { savingRef.current = saving; }, [saving]);

  // Trigger expand animation on mount
  useEffect(() => {
    const timer = requestAnimationFrame(() => {
      setIsExpanded(true);
    });
    return () => cancelAnimationFrame(timer);
  }, []);

  // Update state when switching notes
  useEffect(() => {
    if (initialNote) {
      setNote(initialNote);
      setTitle(initialNote.title);
      setContent(initialNote.content);
      setTags(initialNote.tags || []);
      setLoading(false);
      setHasChanges(false);
      setLastSaved(null);
    }
  }, [notePath, initialNote]);

  useEffect(() => {
    if (initialNote) return;
    
    const loadNote = async () => {
      setLoading(true);
      try {
        const fetchedNote = await getNote(kb, notePath);
        if (fetchedNote) {
          setNote(fetchedNote);
          setTitle(fetchedNote.title);
          setContent(fetchedNote.content);
          setTags(fetchedNote.tags || []);
        }
      } catch (error) {
        console.error('Failed to load note:', error);
      }
      setLoading(false);
    };
    loadNote();
  }, [kb, notePath, getNote, initialNote]);

  const handleTitleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setTitle(e.target.value);
    setHasChanges(true);
  }, []);

  const handleContentChange = useCallback((newContent: string) => {
    setContent(newContent);
    setHasChanges(true);
  }, []);

  const handleTagsChange = useCallback((newTags: string[]) => {
    setTags(newTags);
    setHasChanges(true);
  }, []);

  const handleSave = useCallback(async () => {
    if (!hasChangesRef.current || savingRef.current) return;
    setSaving(true);
    try {
      await onSave(kb, notePath, contentRef.current, titleRef.current, tagsRef.current);
      setHasChanges(false);
      setLastSaved(new Date());
    } finally {
      setSaving(false);
    }
  }, [kb, notePath, onSave]);

  // Debounced autosave
  useEffect(() => {
    if (!hasChanges || saving) return;
    const timer = setTimeout(() => { handleSave(); }, AUTOSAVE_DELAY);
    return () => clearTimeout(timer);
  }, [hasChanges, saving, title, content, tags, handleSave]);

  const handleClose = useCallback(() => {
    if (hasChangesRef.current && !savingRef.current) {
      setSaving(true);
      onSave(kb, notePath, contentRef.current, titleRef.current, tagsRef.current).finally(() => {
        setSaving(false);
        setIsClosing(true);
        setIsExpanded(false);
        setTimeout(onClose, 300);
      });
    } else {
      setIsClosing(true);
      setIsExpanded(false);
      setTimeout(onClose, 300);
    }
  }, [kb, notePath, onSave, onClose]);

  const handleDeleteClick = useCallback(() => {
    setDeleteDialogOpen(true);
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    setDeleteDialogOpen(false);
    await onDelete(kb, notePath);
    onClose();
  }, [kb, notePath, onDelete, onClose]);

  const handleDeleteCancel = useCallback(() => {
    setDeleteDialogOpen(false);
  }, []);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const isThisYear = date.getFullYear() === now.getFullYear();
    
    if (isToday) {
      return `Today at ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`;
    } else if (isThisYear) {
      return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    } else {
      return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
    }
  };

  // Escape and Cmd+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (deleteDialogOpen) return;
      if (e.key === 'Escape') handleClose();
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleClose, handleSave, deleteDialogOpen]);

  const getInitialStyle = () => {
    if (!originRect || isExpanded) return {};
    
    const targetWidth = window.innerWidth;
    const targetHeight = window.innerHeight;
    const scaleX = originRect.width / targetWidth;
    const scaleY = originRect.height / targetHeight;
    const translateX = originRect.x + originRect.width / 2 - targetWidth / 2;
    const translateY = originRect.y + originRect.height / 2 - targetHeight / 2;
    
    return {
      transform: `translate(${translateX}px, ${translateY}px) scale(${scaleX}, ${scaleY})`,
      borderRadius: 'var(--radius-lg)',
    };
  };

  if (loading) {
    return (
      <div className={`${styles['note-editor-fullscreen']} ${isExpanded ? styles['expanded'] : ''}`} style={getInitialStyle()}>
        <div className={styles['note-editor-loading-state']}>Loading...</div>
      </div>
    );
  }

  if (!note) {
    return (
      <div className={`${styles['note-editor-fullscreen']} ${isExpanded ? styles['expanded'] : ''}`} style={getInitialStyle()}>
        <div className={styles['note-editor-error-state']}>
          <p>Note not found</p>
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  return (
    <div 
      className={`${styles['note-editor-fullscreen']} ${isExpanded ? styles['expanded'] : ''} ${isClosing ? styles['closing'] : ''}`}
      style={isExpanded ? {} : getInitialStyle()}
    >
      {/* Fixed header */}
      <div className={`${styles['note-editor-topbar']} ${sidebarOpen ? styles['sidebar-open'] : ''}`}>
        <button className={styles['note-editor-back']} onClick={handleClose} title="Close (Esc)">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
        </button>
        
        <div className={styles['note-editor-status']}>
          {saving && <span className={styles['note-editor-saving']}>Saving...</span>}
          {!saving && hasChanges && <span className={styles['note-editor-unsaved']}>Unsaved</span>}
          {!saving && !hasChanges && lastSaved && <span className={styles['note-editor-saved']}>Saved</span>}
        </div>

        <button 
          className={styles['note-editor-delete']}
          onClick={handleDeleteClick}
          title="Delete note"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
          </svg>
        </button>
      </div>

      {/* Content area */}
      <div className={styles['note-editor-content']}>
        <div className={`${styles['note-editor-paper']} ${sidebarOpen ? styles['paper-sidebar-open'] : ''}`}>
          <input
            type="text"
            value={title}
            onChange={handleTitleChange}
            className={styles['note-editor-title']}
            placeholder="Untitled"
          />

          {/* File path + date */}
          <div className={styles['note-editor-dates']}>
            <span className={styles['note-editor-date']}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              {kb}/{notePath}
            </span>
            <span className={styles['note-editor-date-separator']}>·</span>
            <span className={styles['note-editor-date']}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12 6 12 12 16 14"/>
              </svg>
              Modified {formatDate(note.mtime)}
            </span>
          </div>
          
          <div className={styles['note-editor-tags']}>
            <TagInput
              tags={tags}
              onChange={handleTagsChange}
              placeholder="Add tags..."
            />
          </div>
          <Editor 
            content={content}
            onChange={handleContentChange}
            autoFocus
            kb={kb}
          />
        </div>
      </div>

      <Dialog
        open={deleteDialogOpen}
        title="Delete Note"
        message={`Are you sure you want to delete "${title || 'Untitled'}"?`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
      />
    </div>
  );
}

export default NoteEditor;
