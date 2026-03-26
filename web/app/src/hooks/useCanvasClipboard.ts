import { useCallback, useRef } from 'react';
import type { Node } from '@xyflow/react';
import type { Position } from '../types';

interface ClipboardNode {
  id: string;
  type: string;
  position: Position;
  data: unknown;
}

interface ClipboardData {
  type: 'adjutant-web-nodes';
  nodes: ClipboardNode[];
  origin: Position;
}

// Module-level clipboard storage - persists across component remounts
let moduleClipboard: { nodes: Node[]; position: Position } | null = null;

export function getModuleClipboard() {
  return moduleClipboard;
}

export function setModuleClipboard(data: { nodes: Node[]; position: Position } | null) {
  moduleClipboard = data;
}

interface UseCanvasClipboardProps {
  nodes: Node[];
  screenToFlowPosition: (position: { x: number; y: number }) => Position;
  onImagePaste: (file: File, position: Position) => void;
  onNoteDuplicate: (slug: string, position: Position) => Promise<void>;
  onImageDuplicate: (id: string, position: Position) => Promise<void>;
}

export function useCanvasClipboard({
  nodes,
  screenToFlowPosition,
  onImagePaste,
  onNoteDuplicate,
  onImageDuplicate,
}: UseCanvasClipboardProps) {
  const mousePositionRef = useRef<{ x: number; y: number }>({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
  const contextMenuPositionRef = useRef<Position>({ x: 0, y: 0 });
  const pendingPasteRef = useRef<boolean>(false);

  // Track mouse position for paste operations
  const handleMouseMove = useCallback((e: MouseEvent) => {
    mousePositionRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  // Copy selected nodes to clipboard
  const handleCopyNodes = useCallback(() => {
    const selectedNodes = nodes.filter(n => n.selected);
    if (selectedNodes.length === 0) return;

    const minX = Math.min(...selectedNodes.map(n => n.position.x));
    const minY = Math.min(...selectedNodes.map(n => n.position.y));

    const clipboardData: ClipboardData = {
      type: 'adjutant-web-nodes',
      nodes: selectedNodes.map(n => ({
        id: n.id,
        type: n.type || 'note',
        position: n.position,
        data: n.data,
      })),
      origin: { x: minX, y: minY },
    };

    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(JSON.stringify(clipboardData)).catch(() => {
        // Fallback to memory
      });
    }

    setModuleClipboard({
      nodes: selectedNodes,
      position: { x: minX, y: minY },
    });
  }, [nodes]);

  // Paste nodes at a given position
  const pasteNodesAtPosition = useCallback((pastePosition: Position, data: ClipboardData) => {
    const offsetX = pastePosition.x - data.origin.x;
    const offsetY = pastePosition.y - data.origin.y;

    for (const node of data.nodes) {
      const newPosition = {
        x: node.position.x + offsetX,
        y: node.position.y + offsetY,
      };

      if (node.type === 'note') {
        onNoteDuplicate(node.id, newPosition);
      } else if (node.type === 'image') {
        const imageId = node.id.replace('image-', '');
        onImageDuplicate(imageId, newPosition);
      }
    }
  }, [onNoteDuplicate, onImageDuplicate]);

  // Paste from module clipboard
  const pasteFromModuleClipboard = useCallback((pastePosition: Position) => {
    if (!moduleClipboard) return false;

    const offsetX = pastePosition.x - moduleClipboard.position.x;
    const offsetY = pastePosition.y - moduleClipboard.position.y;

    for (const node of moduleClipboard.nodes) {
      const newPosition = {
        x: node.position.x + offsetX,
        y: node.position.y + offsetY,
      };
      if (node.type === 'note') {
        onNoteDuplicate(node.id, newPosition);
      } else if (node.type === 'image') {
        const imageId = node.id.replace('image-', '');
        onImageDuplicate(imageId, newPosition);
      }
    }
    return true;
  }, [onNoteDuplicate, onImageDuplicate]);

  // Handle paste event (from keyboard Cmd+V)
  const handlePaste = useCallback((event: ClipboardEvent) => {
    const target = event.target as HTMLElement;
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
      return;
    }

    event.preventDefault();

    // Check for image file first
    let imageFile: File | null = null;
    const items = event.clipboardData?.items;
    if (items) {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.startsWith('image/')) {
          imageFile = item.getAsFile();
          break;
        }
      }
    }

    if (imageFile) {
      const pastePosition = screenToFlowPosition({
        x: mousePositionRef.current.x,
        y: mousePositionRef.current.y,
      });
      onImagePaste(imageFile, pastePosition);
      return;
    }

    // Try system clipboard for node data
    const tryPasteFromText = (text: string | null): boolean => {
      if (!text) return false;
      try {
        const data = JSON.parse(text) as ClipboardData;
        if (data.type === 'adjutant-web-nodes' && Array.isArray(data.nodes) && data.nodes.length > 0) {
          const pastePosition = screenToFlowPosition({
            x: mousePositionRef.current.x,
            y: mousePositionRef.current.y,
          });
          pasteNodesAtPosition(pastePosition, data);
          return true;
        }
      } catch {
        // Not valid JSON
      }
      return false;
    };

    if (navigator.clipboard?.readText) {
      navigator.clipboard.readText()
        .then(text => {
          if (!tryPasteFromText(text)) {
            const pastePosition = screenToFlowPosition({
              x: mousePositionRef.current.x,
              y: mousePositionRef.current.y,
            });
            pasteFromModuleClipboard(pastePosition);
          }
        })
        .catch(() => {
          const pastePosition = screenToFlowPosition({
            x: mousePositionRef.current.x,
            y: mousePositionRef.current.y,
          });
          pasteFromModuleClipboard(pastePosition);
        });
    } else {
      const pastePosition = screenToFlowPosition({
        x: mousePositionRef.current.x,
        y: mousePositionRef.current.y,
      });
      pasteFromModuleClipboard(pastePosition);
    }
  }, [screenToFlowPosition, onImagePaste, pasteNodesAtPosition, pasteFromModuleClipboard]);

  return {
    mousePositionRef,
    contextMenuPositionRef,
    pendingPasteRef,
    handleMouseMove,
    handleCopyNodes,
    handlePaste,
    pasteNodesAtPosition,
    pasteFromModuleClipboard,
  };
}
