import { memo, useCallback, useRef, useState, useEffect } from 'react';
import { Handle, Position } from '@xyflow/react';
import styles from './ImageNode.module.css';
import type { CanvasImage } from '../../types';

export interface ImageNodeData extends CanvasImage {
  onResize?: (id: string, width: number, height: number) => void;
  onDelete?: (id: string) => void;
  isPanMode?: boolean;
  [key: string]: unknown;
}

interface ImageNodeProps {
  data: ImageNodeData;
  selected?: boolean;
}

function ImageNodeComponent({ data, selected }: ImageNodeProps) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);
  const [currentSize, setCurrentSize] = useState({
    width: data.displayWidth ?? 200,
    height: data.displayHeight ?? 150,
  });

  // Use refs to avoid stale closures in event handlers
  const resizeStartRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const currentSizeRef = useRef(currentSize);
  currentSizeRef.current = currentSize;

  const isUploading = data.status === 'uploading';
  const isError = data.status === 'error';
  const isReady = data.status === 'ready' || (!isUploading && !isError && data.webpUrl);

  // Sync size from data when not resizing
  useEffect(() => {
    if (!isResizing && data.displayWidth && data.displayHeight) {
      setCurrentSize({ width: data.displayWidth, height: data.displayHeight });
    }
  }, [data.displayWidth, data.displayHeight, isResizing]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (isUploading || isError || data.isPanMode) return;
    e.stopPropagation();
    e.preventDefault();
    
    // Store initial state
    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: currentSizeRef.current.width,
      height: currentSizeRef.current.height,
    };
    setIsResizing(true);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!resizeStartRef.current) return;
      
      const dx = moveEvent.clientX - resizeStartRef.current.x;
      const newWidth = Math.max(50, resizeStartRef.current.width + dx);
      const newHeight = newWidth / data.aspectRatio;
      
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
  }, [isUploading, isError, data.aspectRatio, data.onResize, data.id, data.isPanMode]);

  // Render content based on status
  const renderContent = () => {
    if (isUploading) {
      return (
        <div className={styles['image-node-placeholder']}>
          <div className={styles['image-node-spinner']} />
          <span className={styles['image-node-placeholder-text']}>Pasting image...</span>
        </div>
      );
    }
    
    if (isError) {
      return (
        <div className={`${styles['image-node-placeholder']} ${styles['image-node-error']}`}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          <span className={styles['image-node-placeholder-text']}>Couldn't paste image</span>
          <span className={styles['image-node-error-hint']}>Select and delete to remove</span>
        </div>
      );
    }
    
    return (
      <img
        src={data.webpUrl}
        alt=""
        className={styles['image-node-img']}
        draggable={false}
      />
    );
  };

  return (
    <div 
      ref={nodeRef}
      className={`${styles['image-node']} ${selected ? styles.selected : ''} ${isUploading ? styles.uploading : ''} ${isError ? styles.error : ''}`}
      style={{
        width: currentSize.width,
        height: currentSize.height,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ visibility: 'hidden' }} />
      
      {renderContent()}
      
      {/* Resize handle - only show for ready images */}
      {isReady && (
        <div
          className={`${styles['image-node-resize-handle']} nodrag nopan`}
          onMouseDown={handleMouseDown}
        />
      )}
      
      <Handle type="source" position={Position.Bottom} style={{ visibility: 'hidden' }} />
    </div>
  );
}

export const ImageNode = memo(ImageNodeComponent);
