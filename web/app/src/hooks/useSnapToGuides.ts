import { useCallback, useState } from 'react';
import type { Node } from '@xyflow/react';
import type { GuideLine } from '../components/SnapGuides';

// Default dimensions for snap calculations (fallbacks when measured size unavailable)
const DEFAULT_DIMENSIONS: Record<string, { width: number; height: number }> = {
  note: { width: 200, height: 283 },
  folder: { width: 220, height: 100 },
  section: { width: 500, height: 400 },
  sticky: { width: 150, height: 150 },
  image: { width: 300, height: 200 },
};

// Snap threshold in pixels
const SNAP_THRESHOLD = 8;

interface NodeBounds {
  id: string;
  left: number;
  right: number;
  top: number;
  bottom: number;
  centerX: number;
  centerY: number;
}

function getNodeDimensions(node: Node): { width: number; height: number } {
  // Prefer measured dimensions from React Flow
  if (node.measured?.width && node.measured?.height) {
    return { width: node.measured.width, height: node.measured.height };
  }
  // Try node data (sections store width/height, images store displayWidth/displayHeight)
  const data = node.data as Record<string, unknown> | undefined;
  if (data) {
    const dw = data.displayWidth as number | undefined;
    const dh = data.displayHeight as number | undefined;
    if (dw && dh) return { width: dw, height: dh };
    const w = data.width as number | undefined;
    const h = data.height as number | undefined;
    if (w && h) return { width: w, height: h };
  }
  // Fall back to type-specific defaults
  return DEFAULT_DIMENSIONS[node.type || 'note'] || DEFAULT_DIMENSIONS.note;
}

function getNodeBounds(node: Node): NodeBounds {
  const dims = getNodeDimensions(node);

  return {
    id: node.id,
    left: node.position.x,
    right: node.position.x + dims.width,
    top: node.position.y,
    bottom: node.position.y + dims.height,
    centerX: node.position.x + dims.width / 2,
    centerY: node.position.y + dims.height / 2,
  };
}

export function useSnapToGuides() {
  const [guides, setGuides] = useState<GuideLine[]>([]);

  const calculateSnap = useCallback((
    draggingNode: Node,
    allNodes: Node[]
  ): { x: number; y: number; guides: GuideLine[] } => {
    const dims = getNodeDimensions(draggingNode);
    const dragging = {
      left: draggingNode.position.x,
      right: draggingNode.position.x + dims.width,
      top: draggingNode.position.y,
      bottom: draggingNode.position.y + dims.height,
      centerX: draggingNode.position.x + dims.width / 2,
      centerY: draggingNode.position.y + dims.height / 2,
    };

    // Get bounds of all other nodes
    const otherBounds = allNodes
      .filter(n => n.id !== draggingNode.id)
      .map(getNodeBounds);

    let snapX: number | null = null;
    let snapY: number | null = null;
    const newGuides: GuideLine[] = [];

    // Check vertical alignments (x-axis snapping)
    for (const other of otherBounds) {
      // Left edge to left edge
      if (Math.abs(dragging.left - other.left) < SNAP_THRESHOLD) {
        snapX = other.left;
        newGuides.push({
          type: 'vertical',
          position: other.left,
          start: Math.min(dragging.top, other.top) - 20,
          end: Math.max(dragging.bottom, other.bottom) + 20,
        });
      }
      // Right edge to right edge
      else if (Math.abs(dragging.right - other.right) < SNAP_THRESHOLD) {
        snapX = other.right - dims.width;
        newGuides.push({
          type: 'vertical',
          position: other.right,
          start: Math.min(dragging.top, other.top) - 20,
          end: Math.max(dragging.bottom, other.bottom) + 20,
        });
      }
      // Left edge to right edge
      else if (Math.abs(dragging.left - other.right) < SNAP_THRESHOLD) {
        snapX = other.right;
        newGuides.push({
          type: 'vertical',
          position: other.right,
          start: Math.min(dragging.top, other.top) - 20,
          end: Math.max(dragging.bottom, other.bottom) + 20,
        });
      }
      // Right edge to left edge
      else if (Math.abs(dragging.right - other.left) < SNAP_THRESHOLD) {
        snapX = other.left - dims.width;
        newGuides.push({
          type: 'vertical',
          position: other.left,
          start: Math.min(dragging.top, other.top) - 20,
          end: Math.max(dragging.bottom, other.bottom) + 20,
        });
      }
      // Center to center (vertical)
      else if (Math.abs(dragging.centerX - other.centerX) < SNAP_THRESHOLD) {
        snapX = other.centerX - dims.width / 2;
        newGuides.push({
          type: 'vertical',
          position: other.centerX,
          start: Math.min(dragging.top, other.top) - 20,
          end: Math.max(dragging.bottom, other.bottom) + 20,
        });
      }
    }

    // Check horizontal alignments (y-axis snapping)
    for (const other of otherBounds) {
      // Top edge to top edge
      if (Math.abs(dragging.top - other.top) < SNAP_THRESHOLD) {
        snapY = other.top;
        newGuides.push({
          type: 'horizontal',
          position: other.top,
          start: Math.min(dragging.left, other.left) - 20,
          end: Math.max(dragging.right, other.right) + 20,
        });
      }
      // Bottom edge to bottom edge
      else if (Math.abs(dragging.bottom - other.bottom) < SNAP_THRESHOLD) {
        snapY = other.bottom - dims.height;
        newGuides.push({
          type: 'horizontal',
          position: other.bottom,
          start: Math.min(dragging.left, other.left) - 20,
          end: Math.max(dragging.right, other.right) + 20,
        });
      }
      // Top edge to bottom edge
      else if (Math.abs(dragging.top - other.bottom) < SNAP_THRESHOLD) {
        snapY = other.bottom;
        newGuides.push({
          type: 'horizontal',
          position: other.bottom,
          start: Math.min(dragging.left, other.left) - 20,
          end: Math.max(dragging.right, other.right) + 20,
        });
      }
      // Bottom edge to top edge
      else if (Math.abs(dragging.bottom - other.top) < SNAP_THRESHOLD) {
        snapY = other.top - dims.height;
        newGuides.push({
          type: 'horizontal',
          position: other.top,
          start: Math.min(dragging.left, other.left) - 20,
          end: Math.max(dragging.right, other.right) + 20,
        });
      }
      // Center to center (horizontal)
      else if (Math.abs(dragging.centerY - other.centerY) < SNAP_THRESHOLD) {
        snapY = other.centerY - dims.height / 2;
        newGuides.push({
          type: 'horizontal',
          position: other.centerY,
          start: Math.min(dragging.left, other.left) - 20,
          end: Math.max(dragging.right, other.right) + 20,
        });
      }
    }

    return {
      x: snapX ?? draggingNode.position.x,
      y: snapY ?? draggingNode.position.y,
      guides: newGuides,
    };
  }, []);

  const updateGuides = useCallback((newGuides: GuideLine[]) => {
    setGuides(newGuides);
  }, []);

  const clearGuides = useCallback(() => {
    setGuides([]);
  }, []);

  return {
    guides,
    calculateSnap,
    updateGuides,
    clearGuides,
  };
}
