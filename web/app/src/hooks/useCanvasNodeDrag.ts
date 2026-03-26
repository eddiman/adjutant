import { useCallback, useRef } from 'react';
import type { Node } from '@xyflow/react';
import type { Position, Section } from '../types';
import type { NodeSnapshot, HistoryAction } from './useCanvasHistory';
import type { GuideLine } from '../components/SnapGuides';
import { getSectionContainingNode, isNodeInsideSection } from '../utils/sectionPositioning.js';

interface UseCanvasNodeDragProps<T extends Record<string, unknown>> {
  isTouch: boolean;
  activeTool: string;
  settings: { snapToObject: boolean; showSnapLines: boolean };
  sections: Section[];
  getNodes: () => Node<T>[];
  setNodes: React.Dispatch<React.SetStateAction<Node<T>[]>>;
  calculateSnap: (node: Node<T>, allNodes: Node<T>[]) => { x: number; y: number; guides: GuideLine[] };
  updateGuides: (guides: GuideLine[]) => void;
  clearGuides: () => void;
  historyPush: (action: HistoryAction) => void;
  onNotePositionChange: (slug: string, position: Position) => void;
  onImagePositionChange: (id: string, position: Position) => void;
  onSectionPositionChange: (slug: string, position: Position) => void;
  onStickyPositionChange: (slug: string, position: Position) => void;
  onNoteSectionChange?: (noteSlug: string, sectionSlug: string | null) => void;
}



export function useCanvasNodeDrag<T extends Record<string, unknown>>({
  isTouch,
  activeTool,
  settings,
  sections,
  getNodes,
  setNodes,
  calculateSnap,
  updateGuides,
  clearGuides,
  historyPush,
  onNotePositionChange,
  onImagePositionChange,
  onSectionPositionChange,
  onStickyPositionChange,
  onNoteSectionChange,
}: UseCanvasNodeDragProps<T>) {
  const shiftKeyRef = useRef(false);
  const dragStartPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  // Track which section each note was in at drag start
  const dragStartSectionsRef = useRef<Map<string, string | undefined>>(new Map());
  // Track nodes contained within a dragged section
  const containedNodesRef = useRef<Set<string>>(new Set());
  // Track the section being dragged (if any)
  const draggedSectionRef = useRef<string | null>(null);
  // Track last position for delta calculation during drag
  const lastSectionPositionRef = useRef<{ x: number; y: number } | null>(null);

  // Handle node drag start - capture initial positions for history and auto-select
  const handleNodeDragStart = useCallback((_event: React.MouseEvent, node: Node<T>, draggedNodes: Node<T>[]) => {
    if (isTouch && activeTool === 'pan') return;

    // Auto-select the node if not already selected (and shift is not held)
    if (!node.selected && !shiftKeyRef.current) {
      setNodes(currentNodes =>
        currentNodes.map(n => ({
          ...n,
          selected: n.id === node.id,
        }))
      );
    }

    // Capture starting positions of all dragged nodes
    dragStartPositionsRef.current.clear();
    dragStartSectionsRef.current.clear();
    for (const n of draggedNodes) {
      dragStartPositionsRef.current.set(n.id, { x: n.position.x, y: n.position.y });
      // Capture which section each note is in at drag start
      if (n.type === 'note') {
        const containingSection = getSectionContainingNode(n, sections);
        dragStartSectionsRef.current.set(n.id, containingSection);
      }
    }

    // Check if we're dragging a section - if so, find contained nodes
    containedNodesRef.current.clear();
    draggedSectionRef.current = null;
    lastSectionPositionRef.current = null;

    const draggedSection = draggedNodes.find(n => n.type === 'section');
    if (draggedSection && draggedNodes.length === 1) {
      // Only do grouped movement when dragging a single section
      draggedSectionRef.current = draggedSection.id;
      lastSectionPositionRef.current = { x: draggedSection.position.x, y: draggedSection.position.y };

      const allNodes = getNodes();
      for (const n of allNodes) {
        if (isNodeInsideSection(n, draggedSection)) {
          containedNodesRef.current.add(n.id);
          // Also capture start positions for contained nodes
          dragStartPositionsRef.current.set(n.id, { x: n.position.x, y: n.position.y });
        }
      }
    }
  }, [setNodes, isTouch, activeTool, getNodes, sections]);

  // Handle node drag for snap-to-guides and section grouped movement
  const handleNodeDrag = useCallback((_event: React.MouseEvent, node: Node<T>) => {
    if (isTouch && activeTool === 'pan') return;

    // If dragging a section with contained nodes, move them along
    if (draggedSectionRef.current === node.id && containedNodesRef.current.size > 0 && lastSectionPositionRef.current) {
      const dx = node.position.x - lastSectionPositionRef.current.x;
      const dy = node.position.y - lastSectionPositionRef.current.y;

      if (dx !== 0 || dy !== 0) {
        setNodes(currentNodes =>
          currentNodes.map(n => {
            if (containedNodesRef.current.has(n.id)) {
              return {
                ...n,
                position: {
                  x: n.position.x + dx,
                  y: n.position.y + dy,
                },
              };
            }
            return n;
          })
        );
        lastSectionPositionRef.current = { x: node.position.x, y: node.position.y };
      }
    }

    if (!settings.snapToObject) {
      clearGuides();
      return;
    }

    const allNodes = getNodes();
    const { x, y, guides: newGuides } = calculateSnap(node, allNodes);

    if (settings.showSnapLines) {
      updateGuides(newGuides);
    }

    if (x !== node.position.x || y !== node.position.y) {
      setNodes(currentNodes =>
        currentNodes.map(n =>
          n.id === node.id ? { ...n, position: { x, y } } : n
        )
      );
    }
  }, [getNodes, calculateSnap, updateGuides, clearGuides, setNodes, settings.snapToObject, settings.showSnapLines, isTouch, activeTool]);

  // Handle node drag stop - persist position, push to history, and clear guides
  const handleNodeDragStop = useCallback((_event: React.MouseEvent, _node: Node<T>, draggedNodes: Node<T>[]) => {
    if (isTouch && activeTool === 'pan') return;

    // Get current node positions for contained nodes (they may have moved)
    const allNodes = getNodes();
    const nodePositionMap = new Map(allNodes.map(n => [n.id, n.position]));
    const nodeMap = new Map(allNodes.map(n => [n.id, n]));

    // Build history action from captured start positions
    if (dragStartPositionsRef.current.size > 0) {
      const beforeSnapshots: NodeSnapshot[] = [];
      const afterSnapshots: NodeSnapshot[] = [];

      // Include both dragged nodes and contained nodes in history
      const allAffectedNodeIds = new Set([
        ...draggedNodes.map(n => n.id),
        ...containedNodesRef.current,
      ]);

      for (const nodeId of allAffectedNodeIds) {
        const startPos = dragStartPositionsRef.current.get(nodeId);
        const currentPos = nodePositionMap.get(nodeId);
        if (startPos && currentPos) {
          if (startPos.x !== currentPos.x || startPos.y !== currentPos.y) {
            beforeSnapshots.push({ id: nodeId, position: startPos });
            afterSnapshots.push({ id: nodeId, position: { x: currentPos.x, y: currentPos.y } });
          }
        }
      }

      if (beforeSnapshots.length > 0) {
        historyPush({
          type: 'move',
          description: `Move ${beforeSnapshots.length} node(s)`,
          before: beforeSnapshots,
          after: afterSnapshots,
        });
      }

      dragStartPositionsRef.current.clear();
    }

      // Persist the final positions for all affected nodes
      const nodesToPersist = new Set([
        ...draggedNodes.map(n => n.id),
        ...containedNodesRef.current,
      ]);

      for (const nodeId of nodesToPersist) {
        const position = nodePositionMap.get(nodeId);
        if (!position) continue;

        if (nodeId.startsWith('image-')) {
          const imageId = nodeId.replace('image-', '');
          onImagePositionChange(imageId, position);
        } else if (nodeId.startsWith('section-')) {
          const sectionSlug = nodeId.replace('section-', '');
          onSectionPositionChange(sectionSlug, position);
        } else if (nodeId.startsWith('sticky-')) {
          const stickySlug = nodeId.replace('sticky-', '');
          onStickyPositionChange(stickySlug, position);
        } else {
          onNotePositionChange(nodeId, position);
        }
      }

    // Detect section membership changes for notes
    if (onNoteSectionChange) {
      for (const [noteId, startSection] of dragStartSectionsRef.current) {
        const node = nodeMap.get(noteId);
        if (!node) continue;
        
        const currentSection = getSectionContainingNode(node, sections);
        
        // If section membership changed, notify the callback
        if (startSection !== currentSection) {
          onNoteSectionChange(noteId, currentSection ?? null);
        }
      }
    }
    dragStartSectionsRef.current.clear();

    // Check if section was dragged over new notes that should be included
    if (draggedSectionRef.current && onNoteSectionChange) {
      const draggedSectionNode = nodeMap.get(draggedSectionRef.current);
      if (draggedSectionNode && draggedSectionNode.type === 'section') {
        const sectionData = draggedSectionNode.data as unknown as { slug: string };
        const sectionSlug = sectionData.slug;
        
        // Find all notes and check if they're now inside this section
        for (const [nodeId, node] of nodeMap) {
          if (node.type === 'note') {
            // Skip if note is already in a section
            const noteData = node.data as { section?: string };
            if (noteData.section) continue;
            
            // Check if note is now inside the dragged section
            if (isNodeInsideSection(node, draggedSectionNode)) {
              onNoteSectionChange(nodeId, sectionSlug);
            }
          }
        }
      }
    }

    // Clear section drag tracking
    containedNodesRef.current.clear();
    draggedSectionRef.current = null;
    lastSectionPositionRef.current = null;

    clearGuides();
  }, [getNodes, onNotePositionChange, onImagePositionChange, onSectionPositionChange, onStickyPositionChange, onNoteSectionChange, clearGuides, historyPush, isTouch, activeTool, sections]);

  return {
    shiftKeyRef,
    handleNodeDragStart,
    handleNodeDrag,
    handleNodeDragStop,
  };
}
