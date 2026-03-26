import { useEffect, useRef } from 'react';
import type { Node } from '@xyflow/react';
import { setModuleClipboard } from './useCanvasClipboard';
import type { PlacementType } from '../contexts/PlacementContext.js';

// Helper to check if a node is inside a section's bounds
function isNodeInsideSection<T extends Record<string, unknown>>(
  node: Node<T>,
  section: Node<T>
): boolean {
  // Don't include sections or the section itself
  if (node.type === 'section' || node.id === section.id) return false;

  const sectionData = section.data as { width?: number; height?: number };
  const sectionWidth = sectionData.width || 300;
  const sectionHeight = sectionData.height || 200;

  const nodeWidth = node.measured?.width ?? (node.type === 'note' ? 200 : node.type === 'sticky' ? 150 : 300);
  const nodeHeight = node.measured?.height ?? (node.type === 'note' ? 283 : node.type === 'sticky' ? 150 : 200);

  // Check if node center is inside section bounds
  const nodeCenterX = node.position.x + nodeWidth / 2;
  const nodeCenterY = node.position.y + nodeHeight / 2;

  return (
    nodeCenterX >= section.position.x &&
    nodeCenterX <= section.position.x + sectionWidth &&
    nodeCenterY >= section.position.y &&
    nodeCenterY <= section.position.y + sectionHeight
  );
}

interface UseCanvasKeyboardProps<T extends Record<string, unknown>> {
  deleteDialogOpen: boolean;
  nodes: Node<T>[];
  setNodes: React.Dispatch<React.SetStateAction<Node<T>[]>>;
  getSelectedNoteSlugs: () => string[];
  getSelectedImageIds: () => string[];
  getSelectedSectionSlugs: () => string[];
  getSelectedStickySlugs: () => string[];
  clearSelection: () => void;
  handleUndo: () => void;
  handleRedo: () => void;
  onDeleteRequest: (noteSlugs: string[], imageIds: string[], sectionSlugs?: string[], stickySlugs?: string[]) => void;
  onEnterPlacementMode?: (type: PlacementType) => void;
}

export function useCanvasKeyboard<T extends Record<string, unknown>>({
  deleteDialogOpen,
  nodes,
  setNodes,
  getSelectedNoteSlugs,
  getSelectedImageIds,
  getSelectedSectionSlugs,
  getSelectedStickySlugs,
  clearSelection,
  handleUndo,
  handleRedo,
  onDeleteRequest,
  onEnterPlacementMode,
}: UseCanvasKeyboardProps<T>) {
  // Track mouse position (kept for potential future use)
  const mousePositionRef = useRef({ x: window.innerWidth / 2, y: window.innerHeight / 2 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      mousePositionRef.current = { x: e.clientX, y: e.clientY };
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (deleteDialogOpen) return;
      
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      // Undo: Cmd+Z (Mac) or Ctrl+Z (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
        return;
      }

      // Redo: Cmd+Shift+Z (Mac) or Ctrl+Shift+Z / Ctrl+Y (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && ((e.key === 'z' && e.shiftKey) || e.key === 'y')) {
        e.preventDefault();
        handleRedo();
        return;
      }

      // Copy: Cmd+C (Mac) or Ctrl+C (Windows/Linux)
      if ((e.metaKey || e.ctrlKey) && e.key === 'c') {
        const selectedNodes = nodes.filter(n => n.selected);
        if (selectedNodes.length > 0) {
          e.preventDefault();
          const minX = Math.min(...selectedNodes.map(n => n.position.x));
          const minY = Math.min(...selectedNodes.map(n => n.position.y));

          const clipboardData = {
            type: 'adjutant-web-nodes',
            nodes: selectedNodes.map(n => ({
              id: n.id,
              type: n.type,
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
        }
        return;
      }

      // S key to enter section placement mode
      if (e.key === 's' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (onEnterPlacementMode) {
          onEnterPlacementMode('section');
        }
        return;
      }

      // T key to enter sticky placement mode
      if (e.key === 't' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (onEnterPlacementMode) {
          onEnterPlacementMode('sticky');
        }
        return;
      }

      // Enter key to select all nodes inside selected section(s)
      if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const selectedSections = nodes.filter(n => n.selected && n.type === 'section');
        if (selectedSections.length > 0) {
          e.preventDefault();
          // Find all nodes inside any of the selected sections
          const nodesInsideSections = new Set<string>();
          for (const section of selectedSections) {
            for (const node of nodes) {
              if (isNodeInsideSection(node, section)) {
                nodesInsideSections.add(node.id);
              }
            }
          }
          
          if (nodesInsideSections.size > 0) {
            // Select nodes inside sections, deselect the sections
            setNodes(currentNodes =>
              currentNodes.map(n => ({
                ...n,
                selected: nodesInsideSections.has(n.id),
              }))
            );
          }
        }
        return;
      }

      // Escape to clear selection
      if (e.key === 'Escape') {
        clearSelection();
        return;
      }

      // Delete or Backspace to delete selected notes/images/sections/stickies
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const selectedSlugs = getSelectedNoteSlugs();
        const selectedImageIds = getSelectedImageIds();
        const selectedSectionSlugs = getSelectedSectionSlugs();
        const selectedStickySlugs = getSelectedStickySlugs();
        if (selectedSlugs.length > 0 || selectedImageIds.length > 0 || selectedSectionSlugs.length > 0 || selectedStickySlugs.length > 0) {
          e.preventDefault();
          onDeleteRequest(selectedSlugs, selectedImageIds, selectedSectionSlugs, selectedStickySlugs);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [deleteDialogOpen, clearSelection, getSelectedNoteSlugs, getSelectedImageIds, getSelectedSectionSlugs, getSelectedStickySlugs, handleUndo, handleRedo, nodes, setNodes, onDeleteRequest, onEnterPlacementMode]);
}
