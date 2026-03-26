import { useCallback, useEffect, useState } from 'react';
import type { Node } from '@xyflow/react';
import styles from './SelectionToolbar.module.css';

// Node dimensions for alignment calculations
const NODE_DIMENSIONS = {
  note: { width: 200, height: 283 },
  folder: { width: 220, height: 100 },
} as const;

type AnimationState = 'hidden' | 'entering' | 'expanded' | 'exiting';

interface SelectionToolbarProps {
  selectedNodes: Node[];
  onUpdateNodePositions: (updates: { id: string; x: number; y: number }[]) => void;
}

export function SelectionToolbar({ selectedNodes, onUpdateNodePositions }: SelectionToolbarProps) {
  const [animationState, setAnimationState] = useState<AnimationState>('hidden');
  const shouldShow = selectedNodes.length >= 2;

  // Handle animation state transitions
  useEffect(() => {
    if (shouldShow) {
      // Want to show - start entering if hidden or currently exiting
      if (animationState === 'hidden' || animationState === 'exiting') {
        setAnimationState('entering');
        const timer = setTimeout(() => {
          setAnimationState('expanded');
        }, 500); // Match the full animation duration
        return () => clearTimeout(timer);
      }
    } else {
      // Want to hide - start exiting if visible
      if (animationState === 'expanded' || animationState === 'entering') {
        setAnimationState('exiting');
        const timer = setTimeout(() => {
          setAnimationState('hidden');
        }, 200);
        return () => clearTimeout(timer);
      }
    }
  }, [shouldShow, animationState]);

  // Get node dimensions based on type
  const getNodeDimensions = useCallback((node: Node) => {
    const type = node.type as keyof typeof NODE_DIMENSIONS;
    return NODE_DIMENSIONS[type] || NODE_DIMENSIONS.note;
  }, []);

  // Alignment handlers
  const handleAlignLeft = useCallback(() => {
    if (selectedNodes.length < 2) return;
    const minX = Math.min(...selectedNodes.map(n => n.position.x));
    const updates = selectedNodes.map(node => ({
      id: node.id,
      x: minX,
      y: node.position.y,
    }));
    onUpdateNodePositions(updates);
  }, [selectedNodes, onUpdateNodePositions]);

  const handleAlignRight = useCallback(() => {
    if (selectedNodes.length < 2) return;
    const maxRight = Math.max(...selectedNodes.map(n => {
      const dims = getNodeDimensions(n);
      return n.position.x + dims.width;
    }));
    const updates = selectedNodes.map(node => {
      const dims = getNodeDimensions(node);
      return {
        id: node.id,
        x: maxRight - dims.width,
        y: node.position.y,
      };
    });
    onUpdateNodePositions(updates);
  }, [selectedNodes, onUpdateNodePositions, getNodeDimensions]);

  const handleAlignTop = useCallback(() => {
    if (selectedNodes.length < 2) return;
    const minY = Math.min(...selectedNodes.map(n => n.position.y));
    const updates = selectedNodes.map(node => ({
      id: node.id,
      x: node.position.x,
      y: minY,
    }));
    onUpdateNodePositions(updates);
  }, [selectedNodes, onUpdateNodePositions]);

  const handleAlignBottom = useCallback(() => {
    if (selectedNodes.length < 2) return;
    const maxBottom = Math.max(...selectedNodes.map(n => {
      const dims = getNodeDimensions(n);
      return n.position.y + dims.height;
    }));
    const updates = selectedNodes.map(node => {
      const dims = getNodeDimensions(node);
      return {
        id: node.id,
        x: node.position.x,
        y: maxBottom - dims.height,
      };
    });
    onUpdateNodePositions(updates);
  }, [selectedNodes, onUpdateNodePositions, getNodeDimensions]);

  const handleTidyUp = useCallback(() => {
    if (selectedNodes.length < 2) return;
    
    const GAP = 16;
    
    // Calculate bounding box of selection
    const minX = Math.min(...selectedNodes.map(n => n.position.x));
    const minY = Math.min(...selectedNodes.map(n => n.position.y));
    const maxX = Math.max(...selectedNodes.map(n => {
      const dims = getNodeDimensions(n);
      return n.position.x + dims.width;
    }));
    
    const boundingWidth = maxX - minX;
    
    // Find the widest node to determine column width
    const maxNodeWidth = Math.max(...selectedNodes.map(n => getNodeDimensions(n).width));
    
    // Calculate how many columns fit in the bounding box
    const cols = Math.max(1, Math.floor((boundingWidth + GAP) / (maxNodeWidth + GAP)));
    
    // Sort nodes by their current position (top-to-bottom, left-to-right)
    const sortedNodes = [...selectedNodes].sort((a, b) => {
      const rowA = Math.floor(a.position.y / 100);
      const rowB = Math.floor(b.position.y / 100);
      if (rowA !== rowB) return rowA - rowB;
      return a.position.x - b.position.x;
    });
    
    // Calculate row heights (max height in each row)
    const rowHeights: number[] = [];
    for (let i = 0; i < sortedNodes.length; i++) {
      const rowIndex = Math.floor(i / cols);
      const dims = getNodeDimensions(sortedNodes[i]);
      if (!rowHeights[rowIndex]) {
        rowHeights[rowIndex] = dims.height;
      } else {
        rowHeights[rowIndex] = Math.max(rowHeights[rowIndex], dims.height);
      }
    }
    
    // Position each node in the grid
    const updates = sortedNodes.map((node, index) => {
      const col = index % cols;
      const row = Math.floor(index / cols);
      
      // Calculate y position based on previous row heights
      let y = minY;
      for (let r = 0; r < row; r++) {
        y += rowHeights[r] + GAP;
      }
      
      return {
        id: node.id,
        x: minX + col * (maxNodeWidth + GAP),
        y: y,
      };
    });
    
    onUpdateNodePositions(updates);
  }, [selectedNodes, onUpdateNodePositions, getNodeDimensions]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Check for Alt/Option key
      if (!e.altKey) return;
      if (selectedNodes.length < 2) return;

      // Don't trigger if typing in input
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      // Use e.code for Alt combinations (e.key produces special chars on macOS)
      switch (e.code) {
        case 'KeyA':
          e.preventDefault();
          handleAlignLeft();
          break;
        case 'KeyD':
          e.preventDefault();
          handleAlignRight();
          break;
        case 'KeyW':
          e.preventDefault();
          handleAlignTop();
          break;
        case 'KeyS':
          e.preventDefault();
          handleAlignBottom();
          break;
        case 'KeyT':
          e.preventDefault();
          handleTidyUp();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedNodes, handleAlignLeft, handleAlignRight, handleAlignTop, handleAlignBottom, handleTidyUp]);

  // Don't render if hidden
  if (animationState === 'hidden') {
    return null;
  }

  // Get the animation state class
  const stateClass = styles[`selection-toolbar--${animationState}`];

  return (
    <div className={`${styles['selection-toolbar']} ${stateClass}`}>
      <button
        className={styles['selection-toolbar-button']}
        onClick={handleAlignLeft}
        title="Align Left (⌥A)"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="3" y1="3" x2="3" y2="17" />
          <rect x="6" y="5" width="10" height="3" rx="1" />
          <rect x="6" y="12" width="6" height="3" rx="1" />
        </svg>
      </button>

      <button
        className={styles['selection-toolbar-button']}
        onClick={handleAlignTop}
        title="Align Top (⌥W)"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="3" y1="3" x2="17" y2="3" />
          <rect x="5" y="6" width="3" height="10" rx="1" />
          <rect x="12" y="6" width="3" height="6" rx="1" />
        </svg>
      </button>

      <button
        className={styles['selection-toolbar-button']}
        onClick={handleAlignBottom}
        title="Align Bottom (⌥S)"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="3" y1="17" x2="17" y2="17" />
          <rect x="5" y="4" width="3" height="10" rx="1" />
          <rect x="12" y="8" width="3" height="6" rx="1" />
        </svg>
      </button>

      <button
        className={styles['selection-toolbar-button']}
        onClick={handleAlignRight}
        title="Align Right (⌥D)"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
          <line x1="17" y1="3" x2="17" y2="17" />
          <rect x="4" y="5" width="10" height="3" rx="1" />
          <rect x="8" y="12" width="6" height="3" rx="1" />
        </svg>
      </button>

      <button
        className={styles['selection-toolbar-button']}
        onClick={handleTidyUp}
        title="Tidy Up / Snap to Grid (⌥T)"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
          <rect x="3" y="3" width="5" height="5" rx="1" />
          <rect x="12" y="3" width="5" height="5" rx="1" />
          <rect x="3" y="12" width="5" height="5" rx="1" />
          <rect x="12" y="12" width="5" height="5" rx="1" />
        </svg>
      </button>
    </div>
  );
}
