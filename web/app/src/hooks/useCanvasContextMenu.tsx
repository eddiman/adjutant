import { useCallback, useMemo, useRef, useState } from 'react';
import type { Node } from '@xyflow/react';
import type { Position, KbMeta, StickyColor } from '../types';
import type { ContextMenuItem } from '../components/ContextMenu';

interface ContextMenuState {
  x: number;
  y: number;
  type: 'canvas' | 'node';
  nodeId?: string;
}

interface UseCanvasContextMenuProps<T extends Record<string, unknown>> {
  nodes: Node<T>[];
  categories: KbMeta[];
  screenToFlowPosition: (position: { x: number; y: number }) => Position;
  canUndo: boolean;
  canRedo: boolean;
  handleUndo: () => void;
  handleRedo: () => void;
  handleCopyNodes: () => void;
  handlePasteNodes: () => void;
  handleAddImage: () => void;
  onPlacementClick?: (position: Position, nodes?: Node<T>[]) => void;
  onAddSection?: (position: Position, nodes?: Node<T>[]) => void;
  onAddSticky?: (position: Position) => void;
  onStickyColorChange?: (slug: string, color: StickyColor) => void;
  onSectionColorChange?: (slug: string, color: StickyColor) => void;
  onNoteMoveToCategory?: (slug: string, category: string) => Promise<unknown>;
  onImageMoveToCategory?: (id: string, category: string) => Promise<boolean>;
  onDeleteRequest: (noteSlugs: string[], imageIds: string[], sectionSlugs?: string[], stickySlugs?: string[]) => void;
}

export function useCanvasContextMenu<T extends Record<string, unknown>>({
  nodes,
  categories,
  screenToFlowPosition,
  canUndo,
  canRedo,
  handleUndo,
  handleRedo,
  handleCopyNodes,
  handlePasteNodes,
  handleAddImage,
  onPlacementClick,
  onAddSection,
  onAddSticky,
  onStickyColorChange,
  onSectionColorChange,
  onNoteMoveToCategory,
  onImageMoveToCategory,
  onDeleteRequest,
}: UseCanvasContextMenuProps<T>) {
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const contextMenuPositionRef = useRef<Position>({ x: 0, y: 0 });

  const handleContextMenuClose = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handlePaneContextMenu = useCallback((event: MouseEvent | React.MouseEvent) => {
    event.preventDefault();
    contextMenuPositionRef.current = screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });
    setContextMenu({ x: event.clientX, y: event.clientY, type: 'canvas' });
  }, [screenToFlowPosition]);

  const openContextMenu = useCallback((x: number, y: number, type: 'canvas' | 'node', nodeId?: string) => {
    contextMenuPositionRef.current = screenToFlowPosition({ x, y });
    setContextMenu({ x, y, type, nodeId });
  }, [screenToFlowPosition]);

  // Build context menu items
  const contextMenuItems = useMemo((): ContextMenuItem[] => {
    if (!contextMenu) return [];

    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    const modKey = isMac ? '⌘' : 'Ctrl+';

    if (contextMenu.type === 'canvas') {
      return [
        {
          label: 'Add Note',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" />
            </svg>
          ),
          onClick: () => {
            if (onPlacementClick) {
              onPlacementClick(contextMenuPositionRef.current);
            }
          },
        },
        {
          label: 'Add Sticky',
          shortcut: 'T',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <path d="M8 8h8M8 12h6" />
            </svg>
          ),
          onClick: () => {
            if (onAddSticky) {
              onAddSticky(contextMenuPositionRef.current);
            }
          },
        },
        {
          label: 'Add Section',
          shortcut: 'S',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="4 2" />
            </svg>
          ),
           onClick: () => {
             if (onAddSection) {
               onAddSection(contextMenuPositionRef.current, nodes);
             }
           },
        },
        {
          label: 'Add Image',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          ),
          onClick: handleAddImage,
        },
        { label: '', onClick: () => {}, divider: true },
        {
          label: 'Paste',
          shortcut: `${modKey}V`,
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2" />
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
            </svg>
          ),
          onClick: handlePasteNodes,
          disabled: false,
        },
        { label: '', onClick: () => {}, divider: true },
        {
          label: 'Undo',
          shortcut: `${modKey}Z`,
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 7v6h6" />
              <path d="M21 17a9 9 0 00-9-9 9 9 0 00-6.36 2.64L3 13" />
            </svg>
          ),
          onClick: handleUndo,
          disabled: !canUndo,
        },
        {
          label: 'Redo',
          shortcut: isMac ? '⇧⌘Z' : 'Ctrl+Y',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 7v6h-6" />
              <path d="M3 17a9 9 0 019-9 9 9 0 016.36 2.64L21 13" />
            </svg>
          ),
          onClick: handleRedo,
          disabled: !canRedo,
        },
      ];
    } else {
      // Node context menu
      const selectedNodes = nodes.filter(n => n.selected);
      const selectedNotes = selectedNodes.filter(n => n.type === 'note');
      const selectedImages = selectedNodes.filter(n => n.type === 'image');
      const selectedSections = selectedNodes.filter(n => n.type === 'section');
      const selectedStickies = selectedNodes.filter(n => n.type === 'sticky');
      const hasSelection = selectedNodes.length > 0;
      const selectionLabel = selectedNodes.length === 1 ? 'item' : `${selectedNodes.length} items`;

      // Build "Move to" submenu items (only for notes and images)
      const canMoveToCategory = selectedNotes.length > 0 || selectedImages.length > 0;
      const moveToItems: ContextMenuItem[] = [
        {
          label: 'Uncategorized',
          onClick: async () => {
            for (const n of selectedNotes) {
              if (onNoteMoveToCategory) await onNoteMoveToCategory(n.id, 'all-notes');
            }
            for (const n of selectedImages) {
              const imageId = n.id.replace('image-', '');
              if (onImageMoveToCategory) await onImageMoveToCategory(imageId, 'all-notes');
            }
          },
        },
        ...categories.map(cat => ({
          label: cat.name,
          onClick: async () => {
            for (const n of selectedNotes) {
              if (onNoteMoveToCategory) await onNoteMoveToCategory(n.id, cat.name);
            }
            for (const n of selectedImages) {
              const imageId = n.id.replace('image-', '');
              if (onImageMoveToCategory) await onImageMoveToCategory(imageId, cat.name);
            }
          },
        })),
      ];

      // Build "Change Color" submenu for stickies and sections
      const stickyColors: { label: string; value: StickyColor; hex: string }[] = [
        { label: 'White', value: 'white', hex: '#ffffff' },
        { label: 'Yellow', value: 'yellow', hex: '#fff9c4' },
        { label: 'Pink', value: 'pink', hex: '#f8bbd0' },
        { label: 'Blue', value: 'blue', hex: '#bbdefb' },
        { label: 'Green', value: 'green', hex: '#c8e6c9' },
        { label: 'Purple', value: 'purple', hex: '#e1bee7' },
        { label: 'Orange', value: 'orange', hex: '#ffe0b2' },
        { label: 'Mint', value: 'mint', hex: '#b2dfdb' },
        { label: 'Peach', value: 'peach', hex: '#ffccbc' },
      ];
      
      // Color items for stickies
      const stickyColorItems: ContextMenuItem[] = stickyColors.map(({ label, value, hex }) => ({
        label,
        colorBadge: hex,
        onClick: () => {
          for (const n of selectedStickies) {
            const stickySlug = n.id.replace('sticky-', '');
            if (onStickyColorChange) onStickyColorChange(stickySlug, value);
          }
        },
      }));
      
      // Color items for sections
      const sectionColorItems: ContextMenuItem[] = stickyColors.map(({ label, value, hex }) => ({
        label,
        colorBadge: hex,
        onClick: () => {
          for (const n of selectedSections) {
            const sectionSlug = n.id.replace('section-', '');
            if (onSectionColorChange) onSectionColorChange(sectionSlug, value);
          }
        },
      }));

      const menuItems: ContextMenuItem[] = [
        {
          label: 'Copy',
          shortcut: `${modKey}C`,
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
          ),
          onClick: handleCopyNodes,
          disabled: !hasSelection,
        },
      ];

      // Add "Move to" only if notes or images are selected
      if (canMoveToCategory) {
        menuItems.push(
          { label: '', onClick: () => {}, divider: true },
          {
            label: 'Move to',
            icon: (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
            ),
            onClick: () => {},
            disabled: categories.length === 0,
            submenu: moveToItems,
          }
        );
      }

      // Add "Change Color" only if stickies are selected
      if (selectedStickies.length > 0 && onStickyColorChange) {
        menuItems.push(
          { label: '', onClick: () => {}, divider: true },
          {
            label: 'Change Color',
            icon: (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2a10 10 0 0110 10" />
              </svg>
            ),
            onClick: () => {},
            submenu: stickyColorItems,
          }
        );
      }

      // Add "Change Color" for sections
      if (selectedSections.length > 0 && onSectionColorChange) {
        menuItems.push(
          { label: '', onClick: () => {}, divider: true },
          {
            label: 'Change Color',
            icon: (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 2a10 10 0 0110 10" />
              </svg>
            ),
            onClick: () => {},
            submenu: sectionColorItems,
          }
        );
      }

      // Add delete
      menuItems.push(
        { label: '', onClick: () => {}, divider: true },
        {
          label: `Delete ${selectionLabel}`,
          shortcut: '⌫',
          icon: (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
          ),
          onClick: () => {
            const noteSlugs = selectedNotes.map(n => n.id);
            const imageIds = selectedImages.map(n => n.id.replace('image-', ''));
            const sectionSlugs = selectedSections.map(n => n.id.replace('section-', ''));
            const stickySlugs = selectedStickies.map(n => n.id.replace('sticky-', ''));
            if (noteSlugs.length > 0 || imageIds.length > 0 || sectionSlugs.length > 0 || stickySlugs.length > 0) {
              onDeleteRequest(noteSlugs, imageIds, sectionSlugs, stickySlugs);
            }
          },
          disabled: !hasSelection,
          danger: true,
        }
      );

      return menuItems;
    }
  }, [contextMenu, canUndo, canRedo, handleUndo, handleRedo, handleCopyNodes, handlePasteNodes, handleAddImage, nodes, categories, onNoteMoveToCategory, onImageMoveToCategory, onPlacementClick, onAddSection, onAddSticky, onStickyColorChange, onSectionColorChange, onDeleteRequest]);

  return {
    contextMenu,
    setContextMenu,
    contextMenuPositionRef,
    contextMenuItems,
    handleContextMenuClose,
    handlePaneContextMenu,
    openContextMenu,
  };
}
