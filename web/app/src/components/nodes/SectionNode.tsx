import { memo, useCallback, useRef, useState, useEffect } from 'react';
import { Handle, Position, useViewport } from '@xyflow/react';
import type { Section, StickyColor } from '../../types';
import styles from './SectionNode.module.css';

export interface SectionNodeData extends Section {
  onResize?: (slug: string, width: number, height: number) => void;
  onRename?: (slug: string, name: string) => void;
  onColorChange?: (slug: string, color: StickyColor) => void;
  isPanMode?: boolean;
  [key: string]: unknown;
}

interface SectionNodeProps {
  data: SectionNodeData;
  selected?: boolean;
}

type ResizeCorner = 'tl' | 'tr' | 'bl' | 'br';

function SectionNodeComponent({ data, selected }: SectionNodeProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const { zoom } = useViewport();
  const [isResizing, setIsResizing] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(data.name);
  const [currentSize, setCurrentSize] = useState({
    width: data.width || 300,
    height: data.height || 200,
  });

  // Calculate inverse scale for labels and handles to maintain consistent size
  const inverseScale = 1 / zoom;

  // Refs for resize handling
  const resizeStartRef = useRef<{
    x: number;
    y: number;
    width: number;
    height: number;
    corner: ResizeCorner;
  } | null>(null);
  const currentSizeRef = useRef(currentSize);
  currentSizeRef.current = currentSize;

  // Sync size from data when not resizing
  useEffect(() => {
    if (!isResizing && data.width && data.height) {
      setCurrentSize({ width: data.width, height: data.height });
    }
  }, [data.width, data.height, isResizing]);

  // Sync name from data
  useEffect(() => {
    setEditName(data.name);
  }, [data.name]);

  const handleMouseDown = useCallback((e: React.MouseEvent, corner: ResizeCorner) => {
    if (data.isPanMode) return;
    e.stopPropagation();
    e.preventDefault();

    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: currentSizeRef.current.width,
      height: currentSizeRef.current.height,
      corner,
    };
    setIsResizing(true);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!resizeStartRef.current) return;

      const dx = (moveEvent.clientX - resizeStartRef.current.x) / zoom;
      const dy = (moveEvent.clientY - resizeStartRef.current.y) / zoom;
      const { corner: c, width: startWidth, height: startHeight } = resizeStartRef.current;

      let newWidth = startWidth;
      let newHeight = startHeight;

      // Calculate new size based on which corner is being dragged
      if (c === 'br') {
        newWidth = Math.max(100, startWidth + dx);
        newHeight = Math.max(100, startHeight + dy);
      } else if (c === 'bl') {
        newWidth = Math.max(100, startWidth - dx);
        newHeight = Math.max(100, startHeight + dy);
      } else if (c === 'tr') {
        newWidth = Math.max(100, startWidth + dx);
        newHeight = Math.max(100, startHeight - dy);
      } else if (c === 'tl') {
        newWidth = Math.max(100, startWidth - dx);
        newHeight = Math.max(100, startHeight - dy);
      }

      setCurrentSize({ width: newWidth, height: newHeight });
      currentSizeRef.current = { width: newWidth, height: newHeight };
    };

    const handleMouseUp = () => {
      if (resizeStartRef.current && data.onResize) {
        data.onResize(data.id, currentSizeRef.current.width, currentSizeRef.current.height);
      }
      resizeStartRef.current = null;
      setIsResizing(false);

      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  }, [data.isPanMode, data.onResize, data.id, zoom]);

  // Touch event handler for resize
  const handleTouchStart = useCallback((e: React.TouchEvent, corner: ResizeCorner) => {
    if (data.isPanMode) return;
    e.stopPropagation();
    e.preventDefault();

    const touch = e.touches[0];
    resizeStartRef.current = {
      x: touch.clientX,
      y: touch.clientY,
      width: currentSizeRef.current.width,
      height: currentSizeRef.current.height,
      corner,
    };
    setIsResizing(true);

    const handleTouchMove = (moveEvent: TouchEvent) => {
      if (!resizeStartRef.current) return;
      moveEvent.preventDefault();

      const moveTouch = moveEvent.touches[0];
      const dx = (moveTouch.clientX - resizeStartRef.current.x) / zoom;
      const dy = (moveTouch.clientY - resizeStartRef.current.y) / zoom;
      const { corner: c, width: startWidth, height: startHeight } = resizeStartRef.current;

      let newWidth = startWidth;
      let newHeight = startHeight;

      if (c === 'br') {
        newWidth = Math.max(100, startWidth + dx);
        newHeight = Math.max(100, startHeight + dy);
      } else if (c === 'bl') {
        newWidth = Math.max(100, startWidth - dx);
        newHeight = Math.max(100, startHeight + dy);
      } else if (c === 'tr') {
        newWidth = Math.max(100, startWidth + dx);
        newHeight = Math.max(100, startHeight - dy);
      } else if (c === 'tl') {
        newWidth = Math.max(100, startWidth - dx);
        newHeight = Math.max(100, startHeight - dy);
      }

      setCurrentSize({ width: newWidth, height: newHeight });
      currentSizeRef.current = { width: newWidth, height: newHeight };
    };

    const handleTouchEnd = () => {
      if (resizeStartRef.current && data.onResize) {
        data.onResize(data.id, currentSizeRef.current.width, currentSizeRef.current.height);
      }
      resizeStartRef.current = null;
      setIsResizing(false);

      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleTouchEnd);
    };

    window.addEventListener('touchmove', handleTouchMove, { passive: false });
    window.addEventListener('touchend', handleTouchEnd);
  }, [data.isPanMode, data.onResize, data.id, zoom]);

  const handleNameClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (!data.isPanMode) {
      setIsEditing(true);
    }
  }, [data.isPanMode]);

  const handleNameBlur = useCallback(() => {
    setIsEditing(false);
    if (editName.trim() !== data.name && data.onRename) {
      data.onRename(data.id, editName.trim() || 'Section');
    }
  }, [editName, data.name, data.onRename, data.id]);

  const handleNameKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      (e.target as HTMLInputElement).blur();
    } else if (e.key === 'Escape') {
      setEditName(data.name);
      setIsEditing(false);
    }
  }, [data.name]);

  // Get the CSS color class if using a preset color
  const colorClass = data.color && styles[data.color as StickyColor] ? styles[data.color as StickyColor] : '';

  return (
    <div
      ref={nodeRef}
      className={`${styles['section-node']} ${colorClass} ${selected ? styles.selected : ''}`}
      style={{
        width: currentSize.width,
        height: currentSize.height,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />

      {/* Section name label - scales inversely with zoom */}
      <div 
        className={styles['section-label']}
        style={{
          transform: `scale(${inverseScale})`,
          transformOrigin: 'top left',
        }}
      >
        {isEditing ? (
          <input
            type="text"
            className={styles['section-label-input']}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleNameBlur}
            onKeyDown={handleNameKeyDown}
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className={styles['section-label-text']} onClick={handleNameClick}>
            {data.name}
          </span>
        )}
      </div>

      {/* Corner resize handles - scale inversely with zoom, always visible on mobile when selected */}
      {selected && (
        <>
          <div
            className={`${styles.handle} ${styles['handle-tl']} nodrag nopan`}
            style={{
              transform: `scale(${inverseScale})`,
              transformOrigin: 'center',
            }}
            onMouseDown={(e) => handleMouseDown(e, 'tl')}
            onTouchStart={(e) => handleTouchStart(e, 'tl')}
          />
          <div
            className={`${styles.handle} ${styles['handle-tr']} nodrag nopan`}
            style={{
              transform: `scale(${inverseScale})`,
              transformOrigin: 'center',
            }}
            onMouseDown={(e) => handleMouseDown(e, 'tr')}
            onTouchStart={(e) => handleTouchStart(e, 'tr')}
          />
          <div
            className={`${styles.handle} ${styles['handle-bl']} nodrag nopan`}
            style={{
              transform: `scale(${inverseScale})`,
              transformOrigin: 'center',
            }}
            onMouseDown={(e) => handleMouseDown(e, 'bl')}
            onTouchStart={(e) => handleTouchStart(e, 'bl')}
          />
          <div
            className={`${styles.handle} ${styles['handle-br']} nodrag nopan`}
            style={{
              transform: `scale(${inverseScale})`,
              transformOrigin: 'center',
            }}
            onMouseDown={(e) => handleMouseDown(e, 'br')}
            onTouchStart={(e) => handleTouchStart(e, 'br')}
          />
        </>
      )}

      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </div>
  );
}

export const SectionNode = memo(SectionNodeComponent);
