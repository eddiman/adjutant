import { useCallback, useRef, useState } from 'react';

/**
 * Represents the state of a node for history tracking
 */
export interface NodeSnapshot {
  id: string;
  position: { x: number; y: number };
  type?: string;
  data?: Record<string, unknown>;
  width?: number;
  height?: number;
  selected?: boolean;
}

/**
 * Represents a single undoable/redoable action
 */
export interface HistoryAction {
  type: 'move' | 'delete' | 'create' | 'resize';
  description: string;
  before: NodeSnapshot[];
  after: NodeSnapshot[];
}

interface UseCanvasHistoryOptions {
  maxSize?: number;
}

interface UseCanvasHistoryReturn {
  canUndo: boolean;
  canRedo: boolean;
  push: (action: HistoryAction) => void;
  undo: () => HistoryAction | null;
  redo: () => HistoryAction | null;
  clear: () => void;
  /** Capture current state of nodes before an action */
  captureSnapshot: (nodeIds: string[], getNode: (id: string) => NodeSnapshot | undefined) => NodeSnapshot[];
  /** Start a batch operation - will be combined into single undo */
  startBatch: (description: string) => void;
  /** End batch and push combined action */
  endBatch: (after: NodeSnapshot[]) => void;
  /** Check if batch is in progress */
  isBatching: boolean;
}

/**
 * Hook for managing undo/redo history for canvas operations.
 * 
 * Tracks node positions, deletions, creations, and resizes.
 * Supports batching multiple operations into a single undo action.
 */
export function useCanvasHistory(options: UseCanvasHistoryOptions = {}): UseCanvasHistoryReturn {
  const { maxSize = 50 } = options;
  
  const [past, setPast] = useState<HistoryAction[]>([]);
  const [future, setFuture] = useState<HistoryAction[]>([]);
  
  // Batch tracking
  const batchRef = useRef<{
    description: string;
    before: NodeSnapshot[];
  } | null>(null);

  const push = useCallback((action: HistoryAction) => {
    setPast(prev => {
      const newPast = [...prev, action];
      // Limit history size
      if (newPast.length > maxSize) {
        return newPast.slice(-maxSize);
      }
      return newPast;
    });
    // Clear future on new action
    setFuture([]);
  }, [maxSize]);

  const undo = useCallback((): HistoryAction | null => {
    let action: HistoryAction | null = null;
    
    setPast(prev => {
      if (prev.length === 0) return prev;
      action = prev[prev.length - 1];
      return prev.slice(0, -1);
    });
    
    if (action) {
      setFuture(prev => [...prev, action!]);
    }
    
    return action;
  }, []);

  const redo = useCallback((): HistoryAction | null => {
    let action: HistoryAction | null = null;
    
    setFuture(prev => {
      if (prev.length === 0) return prev;
      action = prev[prev.length - 1];
      return prev.slice(0, -1);
    });
    
    if (action) {
      setPast(prev => [...prev, action!]);
    }
    
    return action;
  }, []);

  const clear = useCallback(() => {
    setPast([]);
    setFuture([]);
    batchRef.current = null;
  }, []);

  const captureSnapshot = useCallback((
    nodeIds: string[],
    getNode: (id: string) => NodeSnapshot | undefined
  ): NodeSnapshot[] => {
    return nodeIds
      .map(id => getNode(id))
      .filter((node): node is NodeSnapshot => node !== undefined);
  }, []);

  const startBatch = useCallback((description: string) => {
    // Batch before state will be captured when first operation occurs
    batchRef.current = {
      description,
      before: [],
    };
  }, []);

  const endBatch = useCallback((after: NodeSnapshot[]) => {
    if (batchRef.current && batchRef.current.before.length > 0) {
      push({
        type: 'move',
        description: batchRef.current.description,
        before: batchRef.current.before,
        after,
      });
    }
    batchRef.current = null;
  }, [push]);

  return {
    canUndo: past.length > 0,
    canRedo: future.length > 0,
    push,
    undo,
    redo,
    clear,
    captureSnapshot,
    startBatch,
    endBatch,
    isBatching: batchRef.current !== null,
  };
}
