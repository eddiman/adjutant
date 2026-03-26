import { useCallback, useEffect, useRef, useState } from 'react';
import type { Node } from '@xyflow/react';
import type { Position } from '../types';

interface UseCanvasTouchGesturesProps<T extends Record<string, unknown>> {
  isTouch: boolean;
  screenToFlowPosition: (position: { x: number; y: number }) => Position;
  getNodes: () => Node<T>[];
  setNodes: React.Dispatch<React.SetStateAction<Node<T>[]>>;
  onContextMenu: (x: number, y: number, type: 'canvas' | 'node', nodeId?: string) => void;
}

export function useCanvasTouchGestures<T extends Record<string, unknown>>({
  isTouch,
  screenToFlowPosition,
  getNodes,
  setNodes,
  onContextMenu,
}: UseCanvasTouchGesturesProps<T>) {
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const longPressTimerRef = useRef<number | null>(null);
  const longPressPosRef = useRef<{ x: number; y: number } | null>(null);
  const twoFingerTapRef = useRef<{ startTime: number; x: number; y: number; initialDistance: number } | null>(null);
  const longPressFiredRef = useRef(false);
  
  const [containerMounted, setContainerMounted] = useState(false);

  // Touch context menu trigger
  const triggerTouchContextMenu = useCallback((clientX: number, clientY: number) => {
    const flowPosition = screenToFlowPosition({ x: clientX, y: clientY });
    const flowNodes = getNodes();

    // Find node under touch point
    const touchedNode = flowNodes.find(node => {
      const nodeWidth = node.measured?.width ?? 200;
      const nodeHeight = node.measured?.height ?? 100;
      return (
        flowPosition.x >= node.position.x &&
        flowPosition.x <= node.position.x + nodeWidth &&
        flowPosition.y >= node.position.y &&
        flowPosition.y <= node.position.y + nodeHeight
      );
    });

    if (touchedNode) {
      if (!touchedNode.selected) {
        setNodes(currentNodes =>
          currentNodes.map(n => ({
            ...n,
            selected: n.id === touchedNode.id,
          }))
        );
      }
      onContextMenu(clientX, clientY, 'node', touchedNode.id);
    } else {
      onContextMenu(clientX, clientY, 'canvas');
    }
  }, [screenToFlowPosition, getNodes, setNodes, onContextMenu]);

  const triggerTouchContextMenuRef = useRef(triggerTouchContextMenu);
  useEffect(() => {
    triggerTouchContextMenuRef.current = triggerTouchContextMenu;
  }, [triggerTouchContextMenu]);

  // Callback ref to detect when container is mounted
  const setCanvasContainerRef = useCallback((node: HTMLDivElement | null) => {
    canvasContainerRef.current = node;
    setContainerMounted(!!node);
  }, []);

  // Native touch event handlers
  useEffect(() => {
    if (!isTouch) return;

    const container = canvasContainerRef.current;
    if (!container) return;

    const clearLongPress = () => {
      if (longPressTimerRef.current) {
        clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = null;
      }
    };

    const handleTouchStart = (e: TouchEvent) => {
      longPressFiredRef.current = false;

      // Two-finger tap detection
      if (e.touches.length === 2) {
        clearLongPress();
        const x = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        const y = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        const dx = e.touches[1].clientX - e.touches[0].clientX;
        const dy = e.touches[1].clientY - e.touches[0].clientY;
        const initialDistance = Math.sqrt(dx * dx + dy * dy);
        twoFingerTapRef.current = { startTime: Date.now(), x, y, initialDistance };
        return;
      }

      // Single finger - start long-press timer
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        longPressPosRef.current = { x: touch.clientX, y: touch.clientY };

        clearLongPress();
        longPressTimerRef.current = window.setTimeout(() => {
          if (longPressPosRef.current) {
            longPressFiredRef.current = true;
            triggerTouchContextMenuRef.current(longPressPosRef.current.x, longPressPosRef.current.y);
          }
        }, 500);
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      // Cancel two-finger tap if fingers move apart (pinch gesture)
      if (twoFingerTapRef.current && e.touches.length === 2) {
        const dx = e.touches[1].clientX - e.touches[0].clientX;
        const dy = e.touches[1].clientY - e.touches[0].clientY;
        const currentDistance = Math.sqrt(dx * dx + dy * dy);
        const distanceChange = Math.abs(currentDistance - twoFingerTapRef.current.initialDistance);

        if (distanceChange > 30) {
          twoFingerTapRef.current = null;
        }
        return;
      }

      if (!longPressPosRef.current || e.touches.length !== 1) return;

      const touch = e.touches[0];
      const dx = Math.abs(touch.clientX - longPressPosRef.current.x);
      const dy = Math.abs(touch.clientY - longPressPosRef.current.y);

      if (dx > 10 || dy > 10) {
        clearLongPress();
      }
    };

    const handleTouchEnd = (e: TouchEvent) => {
      clearLongPress();

      if (longPressFiredRef.current) {
        setTimeout(() => {
          longPressFiredRef.current = false;
        }, 300);
      }

      // Two-finger tap completion
      if (twoFingerTapRef.current && e.touches.length === 0) {
        const elapsed = Date.now() - twoFingerTapRef.current.startTime;
        if (elapsed < 300) {
          triggerTouchContextMenuRef.current(twoFingerTapRef.current.x, twoFingerTapRef.current.y);
        }
        twoFingerTapRef.current = null;
      }
    };

    const handleTouchCancel = () => {
      clearLongPress();
      twoFingerTapRef.current = null;
    };

    container.addEventListener('touchstart', handleTouchStart, { capture: true, passive: true });
    container.addEventListener('touchmove', handleTouchMove, { capture: true, passive: true });
    container.addEventListener('touchend', handleTouchEnd, { capture: true, passive: true });
    container.addEventListener('touchcancel', handleTouchCancel, { capture: true, passive: true });

    return () => {
      clearLongPress();
      container.removeEventListener('touchstart', handleTouchStart, { capture: true });
      container.removeEventListener('touchmove', handleTouchMove, { capture: true });
      container.removeEventListener('touchend', handleTouchEnd, { capture: true });
      container.removeEventListener('touchcancel', handleTouchCancel, { capture: true });
    };
  }, [isTouch, containerMounted]);

  return {
    setCanvasContainerRef,
    longPressFiredRef,
  };
}
