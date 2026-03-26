import { memo, useCallback, useState, useEffect, useRef } from 'react';
import { Handle, Position } from '@xyflow/react';
import type { Sticky, StickyColor } from '../../types';
import styles from './StickyNode.module.css';

export interface StickyNodeData extends Sticky {
  onTextChange?: (slug: string, text: string) => void;
  isPanMode?: boolean;
  [key: string]: unknown;
}

interface StickyNodeProps {
  data: StickyNodeData;
  selected?: boolean;
}

// Detect if device is touch-only
const isTouchDevice = () => {
  if (typeof window === 'undefined') return false;
  return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
};

function StickyNodeComponent({ data, selected }: StickyNodeProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(data.text);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isTouch = useRef(isTouchDevice());
  const lastTapRef = useRef<number>(0);

  // Sync text from data
  useEffect(() => {
    if (!isEditing) {
      setEditText(data.text);
    }
  }, [data.text, isEditing]);

  // Focus textarea when editing starts
  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.select();
    }
  }, [isEditing]);

  // Handle double-click for desktop
  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (!data.isPanMode) {
      setIsEditing(true);
    }
  }, [data.isPanMode]);

  // Handle touch for mobile - single tap when selected, double tap otherwise
  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (data.isPanMode || isEditing) return;
    
    const now = Date.now();
    const timeSinceLastTap = now - lastTapRef.current;
    
    // If selected, single tap to edit
    // If not selected, require double tap
    if (selected || timeSinceLastTap < 300) {
      e.stopPropagation();
      e.preventDefault();
      setIsEditing(true);
    }
    
    lastTapRef.current = now;
  }, [data.isPanMode, selected, isEditing]);

  const handleBlur = useCallback(() => {
    setIsEditing(false);
    // Always save the text when exiting edit mode
    if (data.onTextChange && editText !== data.text) {
      data.onTextChange(data.id, editText);
    }
  }, [editText, data.text, data.onTextChange, data.id]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setEditText(data.text);
      setIsEditing(false);
    }
    // Allow Enter for multiline, but Cmd/Ctrl+Enter to save
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      (e.target as HTMLTextAreaElement).blur();
    }
  }, [data.text]);

  const colorClass = styles[data.color as StickyColor] || styles.yellow;
  const placeholderText = isTouch.current ? 'Tap to edit' : 'Double-click to edit';

  return (
    <div
      className={`${styles['sticky-node']} ${colorClass} ${selected ? styles.selected : ''}`}
      onDoubleClick={handleDoubleClick}
      onTouchEnd={handleTouchEnd}
    >
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />

      {isEditing ? (
        <textarea
          ref={textareaRef}
          className={styles['sticky-input']}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          onClick={(e) => e.stopPropagation()}
          onTouchEnd={(e) => e.stopPropagation()}
          placeholder="Enter text..."
        />
      ) : (
        <div className={styles['sticky-text']}>
          {data.text || placeholderText}
        </div>
      )}

      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </div>
  );
}

export const StickyNode = memo(StickyNodeComponent);
