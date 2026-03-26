import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Controls,
  useNodesState,
  useReactFlow,
  ReactFlowProvider,
  SelectionMode,
  PanOnScrollMode,
  type Node,
  type NodeChange,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { NoteNode, type NoteNodeData, type OriginRect } from '../nodes/NoteNode';
import { ImageNode, type ImageNodeData } from '../nodes/ImageNode';
import { SectionNode, type SectionNodeData } from '../nodes/SectionNode';
import { StickyNode, type StickyNodeData } from '../nodes/StickyNode';
import { Dialog } from '../Dialog';
import { SnapGuides } from '../SnapGuides';
import { AdaptiveBackground } from '../AdaptiveBackground';
import { ContextMenu } from '../ContextMenu';
import { CanvasLoader } from './CanvasLoader';
import { useSnapToGuides } from '../../hooks/useSnapToGuides';
import { useCanvasHistory, type NodeSnapshot } from '../../hooks/useCanvasHistory';
import { useCanvasClipboard } from '../../hooks/useCanvasClipboard';
import { useCanvasContextMenu } from '../../hooks/useCanvasContextMenu';
import { useCanvasTouchGestures } from '../../hooks/useCanvasTouchGestures';
import { useCanvasNodeDrag } from '../../hooks/useCanvasNodeDrag';
import { useCanvasKeyboard } from '../../hooks/useCanvasKeyboard';
import { isTouchDevice } from '../../utils/platform.js';
import type { NoteFile, Position, CanvasImage, KbMeta, CanvasTool, Section, Sticky, StickyColor } from '../../types';
import type { PlacementType } from '../../contexts/PlacementContext.js';
import type { Settings } from '../../hooks/useSettings';
import styles from './Canvas.module.css';

type CanvasNodeData = NoteNodeData | ImageNodeData | SectionNodeData | StickyNodeData;

export type { OriginRect };

export interface CanvasHistoryHandle {
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export interface FocusOnNodeOptions {
  zoom?: number;
  duration?: number;
}

interface CanvasProps {
  notes: NoteFile[];
  images: CanvasImage[];
  sections: Section[];
  stickies: Sticky[];
  categories: KbMeta[];
  activeTool?: CanvasTool;
  isPlacementMode?: boolean;
  onPlacementClick?: (position: Position, nodes?: Node<CanvasNodeData>[]) => void;
  onNoteOpen: (notePath: string, originRect: OriginRect) => void;
  onNotePositionChange: (slug: string, position: Position) => void;
  onImagePositionChange: (id: string, position: Position) => void;
  onImageResize: (id: string, width: number, height: number) => void;
  onImagePaste: (file: File, position: Position) => void;
  onNotesDelete: (slugs: string[]) => Promise<void>;
  onImagesDelete: (ids: string[]) => Promise<void>;
  onNoteDuplicate: (slug: string, position: Position) => Promise<void>;
  onImageDuplicate: (id: string, position: Position) => Promise<void>;
  onNoteMoveToCategory?: (slug: string, category: string) => Promise<NoteFile | null>;
  onImageMoveToCategory?: (id: string, category: string) => Promise<boolean>;
  onNoteSectionChange?: (noteSlug: string, sectionSlug: string | null) => void;
  // Section handlers
  onSectionCreate?: (position: Position, nodes?: Node<CanvasNodeData>[]) => void;
  onSectionPositionChange: (slug: string, position: Position) => void;
  onSectionResize: (slug: string, width: number, height: number) => void;
  onSectionRename: (slug: string, name: string) => void;
  onSectionColorChange?: (slug: string, color: StickyColor) => void;
  onSectionsDelete?: (slugs: string[]) => Promise<void>;
  // Sticky handlers
  onStickyCreate?: (position: Position) => void;
  onStickyPositionChange: (slug: string, position: Position) => void;
  onStickyTextChange: (slug: string, text: string) => void;
  onStickyColorChange?: (slug: string, color: StickyColor) => void;
  onStickiesDelete?: (slugs: string[]) => Promise<void>;
  onSelectionChange?: (selectedNodes: Node<CanvasNodeData>[]) => void;
  onUpdateNodePositionsRef?: (handler: (updates: NodePositionUpdate[]) => void) => void;
  onFocusOnNodeRef?: (handler: (nodeId: string, options?: FocusOnNodeOptions) => void) => void;
  onEnterPlacementMode?: (type: PlacementType) => void;
  onHistoryChange?: (history: CanvasHistoryHandle) => void;
  loading: boolean;
  settings: Settings;
}

export interface NodePositionUpdate {
  id: string;
  x: number;
  y: number;
}

const nodeTypes: NodeTypes = {
  note: NoteNode,
  image: ImageNode,
  section: SectionNode,
  sticky: StickyNode,
};

function getDefaultPosition(index: number): Position {
  const cols = 4;
  const noteWidth = 200;
  const noteHeight = 283;
  const gap = 60;
  const col = index % cols;
  const row = Math.floor(index / cols);
  return {
    x: col * (noteWidth + gap),
    y: row * (noteHeight + gap),
  };
}

export function Canvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

function CanvasInner({
  notes,
  images,
  sections,
  stickies,
  categories,
  activeTool = 'select',
  isPlacementMode = false,
  onPlacementClick,
  onNoteOpen,
  onNotePositionChange,
  onImagePositionChange,
  onImageResize,
  onImagePaste,
  onNotesDelete,
  onImagesDelete,
  onNoteDuplicate,
  onImageDuplicate,
  onNoteMoveToCategory,
  onImageMoveToCategory,
  onNoteSectionChange,
  onSectionCreate,
  onSectionPositionChange,
  onSectionResize,
  onSectionRename,
  onSectionColorChange,
  onSectionsDelete,
  onStickyCreate,
  onStickyPositionChange,
  onStickyTextChange,
  onStickyColorChange,
  onStickiesDelete,
  onSelectionChange,
  onUpdateNodePositionsRef,
  onFocusOnNodeRef,
  onEnterPlacementMode,
  onHistoryChange,
  loading,
  settings,
}: CanvasProps) {
  const { getNodes, screenToFlowPosition, setCenter } = useReactFlow<Node<CanvasNodeData>>();
  const { guides, calculateSnap, updateGuides, clearGuides } = useSnapToGuides();
  const history = useCanvasHistory();
  
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [notesToDelete, setNotesToDelete] = useState<string[]>([]);
  const [imagesToDelete, setImagesToDelete] = useState<string[]>([]);
  const [sectionsToDelete, setSectionsToDelete] = useState<string[]>([]);
  const [stickiesToDelete, setStickiesToDelete] = useState<string[]>([]);
  const [isAnimating, setIsAnimating] = useState(false);
  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);
  const [pasteInputPosition, setPasteInputPosition] = useState<{ x: number; y: number; visible: boolean }>({ x: 0, y: 0, visible: false });
  const [showLoader, setShowLoader] = useState(loading);
  const [isEntering, setIsEntering] = useState(false);
  
  const imageInputRef = useRef<HTMLInputElement>(null);
  const pasteTargetRef = useRef<HTMLInputElement>(null);

  const isTouch = useMemo(() => isTouchDevice(), []);

  // Delete request handler
  const handleDeleteRequest = useCallback((noteSlugs: string[], imageIds: string[], sectionSlugs?: string[], stickySlugs?: string[]) => {
    setNotesToDelete(noteSlugs);
    setImagesToDelete(imageIds);
    setSectionsToDelete(sectionSlugs || []);
    setStickiesToDelete(stickySlugs || []);
    setDeleteDialogOpen(true);
  }, []);

  // Clipboard hook
  const clipboard = useCanvasClipboard({
    nodes: [],
    screenToFlowPosition,
    onImagePaste,
    onNoteDuplicate,
    onImageDuplicate,
  });

  // Apply history state
  const applyHistoryState = useCallback((snapshots: NodeSnapshot[]) => {
    const positionMap = new Map(snapshots.map(s => [s.id, { x: s.position.x, y: s.position.y }]));
    setNodes(currentNodes =>
      currentNodes.map(node => {
        const pos = positionMap.get(node.id);
        if (pos) {
          return { ...node, position: pos };
        }
        return node;
      })
    );
    for (const snapshot of snapshots) {
      if (snapshot.id.startsWith('image-')) {
        const imageId = snapshot.id.replace('image-', '');
        onImagePositionChange(imageId, snapshot.position);
      } else if (snapshot.id.startsWith('section-')) {
        const sectionSlug = snapshot.id.replace('section-', '');
        onSectionPositionChange(sectionSlug, snapshot.position);
      } else if (snapshot.id.startsWith('sticky-')) {
        const stickySlug = snapshot.id.replace('sticky-', '');
        onStickyPositionChange(stickySlug, snapshot.position);
      } else {
        onNotePositionChange(snapshot.id, snapshot.position);
      }
    }
  }, [onNotePositionChange, onImagePositionChange, onSectionPositionChange, onStickyPositionChange]);

  const handleUndo = useCallback(() => {
    const action = history.undo();
    if (action) applyHistoryState(action.before);
  }, [history, applyHistoryState]);

  const handleRedo = useCallback(() => {
    const action = history.redo();
    if (action) applyHistoryState(action.after);
  }, [history, applyHistoryState]);

  // Add image handler
  const handleAddImage = useCallback(() => {
    imageInputRef.current?.click();
  }, []);

  const handleImageInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      const pastePosition = clipboard.contextMenuPositionRef.current;
      onImagePaste(file, pastePosition);
    }
    if (imageInputRef.current) {
      imageInputRef.current.value = '';
    }
  }, [onImagePaste, clipboard.contextMenuPositionRef]);

  // Convert notes, images, sections, and stickies to React Flow nodes
  const initialNodes: Node<CanvasNodeData>[] = useMemo(() => {
    const isPanMode = isTouch && activeTool === 'pan';

    // Sections render first (behind everything else)
    const sectionNodes: Node<SectionNodeData>[] = sections.map((section, index) => ({
      id: `section-${section.id}`,
      type: 'section',
      position: section.position || getDefaultPosition(index),
      data: {
        ...section,
        onResize: onSectionResize,
        onRename: onSectionRename,
        isPanMode,
      },
      draggable: !isPanMode,
      selected: false,
      zIndex: -1, // Ensure sections are behind other nodes
    }));

    const noteNodes: Node<NoteNodeData>[] = notes.map((note, index) => ({
      id: `note-${note.filename}`,
      type: 'note',
      position: note.position || getDefaultPosition(index),
      data: {
        ...note,
        onOpen: onNoteOpen,
        isPanMode,
      },
      draggable: !isPanMode,
      selected: false,
    }));

    const imageNodes: Node<ImageNodeData>[] = images.map((image, index) => ({
      id: `image-${image.id}`,
      type: 'image',
      position: image.position || getDefaultPosition(notes.length + index),
      data: {
        ...image,
        onResize: (id: string, width: number, height: number) => {
          onImageResize(id, width, height);
        },
        isPanMode,
      },
      draggable: !isPanMode,
      selected: false,
    }));

    const stickyNodes: Node<StickyNodeData>[] = stickies.map((sticky, index) => ({
      id: `sticky-${sticky.id}`,
      type: 'sticky',
      position: sticky.position || getDefaultPosition(notes.length + images.length + index),
      data: {
        ...sticky,
        onTextChange: onStickyTextChange,
        isPanMode,
      },
      draggable: !isPanMode,
      selected: false,
    }));

    // Sections first (behind), then notes, images, stickies
    return [...sectionNodes, ...noteNodes, ...imageNodes, ...stickyNodes];
  }, [notes, images, sections, stickies, categories, onNoteOpen, onImageResize, onSectionResize, onSectionRename, onStickyTextChange, isTouch, activeTool]);

  const nodeStructureKey = useMemo(() => {
    const noteKey = notes.map(n => `${n.filename}:${n.kb}`).join('|');
    const imageKey = images.map(i => `${i.id}:${i.displayWidth}:${i.status}`).join('|');
    const sectionKey = sections.map(s => `${s.id}:${s.width}:${s.height}`).join('|');
    const stickyKey = stickies.map(s => `${s.id}:${s.color}`).join('|');
    return `${noteKey}::${imageKey}::${sectionKey}::${stickyKey}`;
  }, [notes, images, sections, stickies]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);

  const initialNodesRef = useRef(initialNodes);
  initialNodesRef.current = initialNodes;

  // Sync nodes when structure changes
  useEffect(() => {
    setNodes(currentNodes => {
      const selectionMap = new Map(currentNodes.map(n => [n.id, n.selected ?? false]));
      const positionMap = new Map(currentNodes.map(n => [n.id, n.position]));

      return initialNodesRef.current.map(node => ({
        ...node,
        position: positionMap.get(node.id) ?? node.position,
        selected: selectionMap.get(node.id) ?? false,
      }));
    });
  }, [nodeStructureKey, setNodes]);

  // Sync node data when content changes
  useEffect(() => {
    const noteDataMap = new Map(notes.map(n => [`note-${n.filename}`, n]));
    const imageDataMap = new Map(images.map(i => [`image-${i.id}`, i]));
    const sectionDataMap = new Map(sections.map(s => [`section-${s.id}`, s]));
    const stickyDataMap = new Map(stickies.map(s => [`sticky-${s.id}`, s]));

    setNodes(currentNodes =>
      currentNodes.map(node => {
        if (node.type === 'note') {
          const noteData = noteDataMap.get(node.id);
          if (noteData && (noteData.title !== (node.data as NoteNodeData).title ||
            noteData.content !== (node.data as NoteNodeData).content)) {
            return { ...node, data: { ...node.data, ...noteData } };
          }
        } else if (node.type === 'image') {
          const imageData = imageDataMap.get(node.id);
          if (imageData) {
            return { ...node, data: { ...node.data, ...imageData } };
          }
        } else if (node.type === 'section') {
          const sectionData = sectionDataMap.get(node.id);
          if (sectionData) {
            const currentData = node.data as SectionNodeData;
            if (sectionData.name !== currentData.name || sectionData.color !== currentData.color) {
              return { ...node, data: { ...node.data, ...sectionData } };
            }
          }
        } else if (node.type === 'sticky') {
          const stickyData = stickyDataMap.get(node.id);
          if (stickyData) {
            const currentData = node.data as StickyNodeData;
            if (stickyData.text !== currentData.text || stickyData.color !== currentData.color) {
              return { ...node, data: { ...node.data, ...stickyData } };
            }
          }
        }
        return node;
      })
    );
  }, [notes, images, sections, stickies, setNodes]);

  // Sync isPanMode when tool changes
  useEffect(() => {
    const isPanMode = isTouch && activeTool === 'pan';
    setNodes(currentNodes =>
      currentNodes.map(node => ({
        ...node,
        draggable: !isPanMode,
        data: { ...node.data, isPanMode },
      }))
    );
  }, [activeTool, isTouch, setNodes]);

  // Sync highlighted node
  useEffect(() => {
    setNodes(currentNodes =>
      currentNodes.map(node => {
        if (node.type !== 'note') return node;
        const isHighlighted = node.id === highlightedNodeId;
        if ((node.data as NoteNodeData).isHighlighted === isHighlighted) return node;
        return { ...node, data: { ...node.data, isHighlighted } };
      })
    );
  }, [highlightedNodeId, setNodes]);

  // Selection helpers
  const getSelectedNoteSlugs = useCallback(() => {
    return nodes.filter(n => n.selected && n.type === 'note').map(n => n.id);
  }, [nodes]);

  const getSelectedImageIds = useCallback(() => {
    return nodes.filter(n => n.selected && n.type === 'image').map(n => n.id.replace('image-', ''));
  }, [nodes]);

  const getSelectedSectionSlugs = useCallback(() => {
    return nodes.filter(n => n.selected && n.type === 'section').map(n => n.id.replace('section-', ''));
  }, [nodes]);

  const getSelectedStickySlugs = useCallback(() => {
    return nodes.filter(n => n.selected && n.type === 'sticky').map(n => n.id.replace('sticky-', ''));
  }, [nodes]);

  const clearSelection = useCallback(() => {
    setNodes(currentNodes => currentNodes.map(n => ({ ...n, selected: false })));
  }, [setNodes]);

  // Handle section creation with nodes context
  const handleSectionCreateWithNodes = useCallback((position: Position) => {
    if (onSectionCreate) {
      const allNodes = getNodes();
      onSectionCreate(position, allNodes);
    }
  }, [onSectionCreate, getNodes]);

  // Context menu hook
  const contextMenuHook = useCanvasContextMenu<CanvasNodeData>({
    nodes,
    categories,
    screenToFlowPosition,
    canUndo: history.canUndo,
    canRedo: history.canRedo,
    handleUndo,
    handleRedo,
    handleCopyNodes: clipboard.handleCopyNodes,
    handlePasteNodes: () => {
      clipboard.pendingPasteRef.current = true;
      const screenPos = contextMenuHook.contextMenu
        ? { x: contextMenuHook.contextMenu.x, y: contextMenuHook.contextMenu.y }
        : { x: window.innerWidth / 2, y: window.innerHeight / 2 };
      setPasteInputPosition({ x: screenPos.x, y: screenPos.y, visible: true });
      if (pasteTargetRef.current) {
        pasteTargetRef.current.focus();
        pasteTargetRef.current.select();
        try {
          document.execCommand('paste');
        } catch { /* ignore */ }
      }
      contextMenuHook.setContextMenu(null);
    },
    handleAddImage,
    onPlacementClick,
    onAddSection: handleSectionCreateWithNodes,
    onAddSticky: onStickyCreate,
    onStickyColorChange,
    onSectionColorChange,
    onNoteMoveToCategory,
    onImageMoveToCategory,
    onDeleteRequest: handleDeleteRequest,
  });

  // Touch gestures hook
  const touchGestures = useCanvasTouchGestures<CanvasNodeData>({
    isTouch,
    screenToFlowPosition,
    getNodes,
    setNodes,
    onContextMenu: contextMenuHook.openContextMenu,
  });

  // Node drag hook
  const nodeDrag = useCanvasNodeDrag<CanvasNodeData>({
    isTouch,
    activeTool,
    settings,
    sections,
    getNodes,
    setNodes,
    calculateSnap,
    updateGuides,
    clearGuides,
    historyPush: history.push,
    onNotePositionChange,
    onImagePositionChange,
    onSectionPositionChange,
    onStickyPositionChange,
    onNoteSectionChange,
  });

  // Keyboard shortcuts
  useCanvasKeyboard({
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
    onDeleteRequest: handleDeleteRequest,
    onEnterPlacementMode,
  });

  // Track shift key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Shift') nodeDrag.shiftKeyRef.current = true;
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'Shift') nodeDrag.shiftKeyRef.current = false;
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [nodeDrag.shiftKeyRef]);

  // Track mouse position
  useEffect(() => {
    window.addEventListener('mousemove', clipboard.handleMouseMove);
    return () => window.removeEventListener('mousemove', clipboard.handleMouseMove);
  }, [clipboard.handleMouseMove]);

  // Paste listener
  useEffect(() => {
    document.addEventListener('paste', clipboard.handlePaste);
    return () => document.removeEventListener('paste', clipboard.handlePaste);
  }, [clipboard.handlePaste]);

  // Selection change callback
  useEffect(() => {
    if (onSelectionChange) {
      const selectedNodes = nodes.filter(n => n.selected);
      onSelectionChange(selectedNodes);
    }
  }, [nodes, onSelectionChange]);

  // Expose history handle
  const historyHandleRef = useRef<CanvasHistoryHandle>({
    undo: () => {},
    redo: () => {},
    canUndo: false,
    canRedo: false,
  });

  historyHandleRef.current = {
    undo: handleUndo,
    redo: handleRedo,
    canUndo: history.canUndo,
    canRedo: history.canRedo,
  };

  useEffect(() => {
    if (onHistoryChange) {
      onHistoryChange({
        undo: () => historyHandleRef.current.undo(),
        redo: () => historyHandleRef.current.redo(),
        get canUndo() { return historyHandleRef.current.canUndo; },
        get canRedo() { return historyHandleRef.current.canRedo; },
      });
    }
  }, [onHistoryChange]);

  // Update node positions handler
  const updateNodePositions = useCallback((updates: NodePositionUpdate[]) => {
    const beforeSnapshots: NodeSnapshot[] = updates.map(u => {
      const node = nodes.find(n => n.id === u.id);
      return { id: u.id, position: node?.position ?? { x: 0, y: 0 } };
    });

    const afterSnapshots: NodeSnapshot[] = updates.map(u => ({
      id: u.id,
      position: { x: u.x, y: u.y },
    }));

    history.push({
      type: 'move',
      description: 'Align nodes',
      before: beforeSnapshots,
      after: afterSnapshots,
    });

    setIsAnimating(true);

    setNodes(currentNodes => {
      const updateMap = new Map(updates.map(u => [u.id, { x: u.x, y: u.y }]));
      return currentNodes.map(node => {
        const update = updateMap.get(node.id);
        if (update) {
          return { ...node, position: update, selected: node.selected };
        }
        return node;
      });
    });

    setTimeout(() => setIsAnimating(false), 300);

    for (const update of updates) {
      if (update.id.startsWith('image-')) {
        const imageId = update.id.replace('image-', '');
        onImagePositionChange(imageId, { x: update.x, y: update.y });
      } else if (update.id.startsWith('section-')) {
        const sectionSlug = update.id.replace('section-', '');
        onSectionPositionChange(sectionSlug, { x: update.x, y: update.y });
      } else if (update.id.startsWith('sticky-')) {
        const stickySlug = update.id.replace('sticky-', '');
        onStickyPositionChange(stickySlug, { x: update.x, y: update.y });
      } else {
        onNotePositionChange(update.id, { x: update.x, y: update.y });
      }
    }
  }, [setNodes, onNotePositionChange, onImagePositionChange, onSectionPositionChange, onStickyPositionChange, nodes, history]);

  useEffect(() => {
    if (onUpdateNodePositionsRef) {
      onUpdateNodePositionsRef(updateNodePositions);
    }
  }, [onUpdateNodePositionsRef, updateNodePositions]);

  // Focus on node
  const focusOnNode = useCallback((nodeId: string, options?: FocusOnNodeOptions) => {
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;

    const nodeWidth = node.measured?.width ?? (node.type === 'note' ? 200 : 300);
    const nodeHeight = node.measured?.height ?? (node.type === 'note' ? 283 : 200);
    const centerX = node.position.x + nodeWidth / 2;
    const centerY = node.position.y + nodeHeight / 2;

    const zoom = options?.zoom ?? 1;
    const duration = options?.duration ?? 800;

    setCenter(centerX, centerY, { zoom, duration });

    setTimeout(() => {
      setHighlightedNodeId(nodeId);
      setTimeout(() => setHighlightedNodeId(null), 800);
    }, duration);
  }, [nodes, setCenter]);

  useEffect(() => {
    if (onFocusOnNodeRef) {
      onFocusOnNodeRef(focusOnNode);
    }
  }, [onFocusOnNodeRef, focusOnNode]);

  // Delete handlers
  const handleDeleteConfirm = useCallback(async () => {
    if (notesToDelete.length > 0) {
      await onNotesDelete(notesToDelete);
      setNotesToDelete([]);
    }
    if (imagesToDelete.length > 0) {
      await onImagesDelete(imagesToDelete);
      setImagesToDelete([]);
    }
    if (sectionsToDelete.length > 0 && onSectionsDelete) {
      await onSectionsDelete(sectionsToDelete);
      setSectionsToDelete([]);
    }
    if (stickiesToDelete.length > 0 && onStickiesDelete) {
      await onStickiesDelete(stickiesToDelete);
      setStickiesToDelete([]);
    }
    setDeleteDialogOpen(false);
  }, [notesToDelete, onNotesDelete, imagesToDelete, onImagesDelete, sectionsToDelete, onSectionsDelete, stickiesToDelete, onStickiesDelete]);

  const handleDeleteCancel = useCallback(() => {
    setDeleteDialogOpen(false);
    setNotesToDelete([]);
    setImagesToDelete([]);
    setSectionsToDelete([]);
    setStickiesToDelete([]);
  }, []);

  const getDeleteDialogMessage = () => {
    const totalCount = notesToDelete.length + imagesToDelete.length + sectionsToDelete.length + stickiesToDelete.length;
    if (totalCount === 1) {
      if (notesToDelete.length === 1) {
        const note = notes.find(n => `note-${n.filename}` === notesToDelete[0]);
        return `Are you sure you want to delete "${note?.title || 'Untitled'}"?`;
      } else if (imagesToDelete.length === 1) {
        return `Are you sure you want to delete this image?`;
      } else if (sectionsToDelete.length === 1) {
        return `Are you sure you want to delete this section?`;
      } else {
        return `Are you sure you want to delete this sticky note?`;
      }
    }
    const parts = [];
    if (notesToDelete.length > 0) {
      parts.push(`${notesToDelete.length} note${notesToDelete.length > 1 ? 's' : ''}`);
    }
    if (imagesToDelete.length > 0) {
      parts.push(`${imagesToDelete.length} image${imagesToDelete.length > 1 ? 's' : ''}`);
    }
    if (sectionsToDelete.length > 0) {
      parts.push(`${sectionsToDelete.length} section${sectionsToDelete.length > 1 ? 's' : ''}`);
    }
    if (stickiesToDelete.length > 0) {
      parts.push(`${stickiesToDelete.length} sticky note${stickiesToDelete.length > 1 ? 's' : ''}`);
    }
    return `Are you sure you want to delete ${parts.join(' and ')}?`;
  };

  const getDeleteDialogTitle = () => {
    const hasNotes = notesToDelete.length > 0;
    const hasImages = imagesToDelete.length > 0;
    const hasSections = sectionsToDelete.length > 0;
    const hasStickies = stickiesToDelete.length > 0;
    const typeCount = [hasNotes, hasImages, hasSections, hasStickies].filter(Boolean).length;
    
    if (typeCount > 1) return 'Delete Items';
    
    if (hasImages) return imagesToDelete.length === 1 ? 'Delete Image' : 'Delete Images';
    if (hasNotes) return notesToDelete.length === 1 ? 'Delete Note' : 'Delete Notes';
    if (hasSections) return sectionsToDelete.length === 1 ? 'Delete Section' : 'Delete Sections';
    if (hasStickies) return stickiesToDelete.length === 1 ? 'Delete Sticky Note' : 'Delete Sticky Notes';
    
    return 'Delete Items';
  };

  // Handle node changes
  const handleNodesChange = useCallback((changes: NodeChange<Node<CanvasNodeData>>[]) => {
    if (isTouch && activeTool === 'pan') {
      const nonSelectionChanges = changes.filter(change => change.type !== 'select');
      if (nonSelectionChanges.length === 0) return;
      onNodesChange(nonSelectionChanges);

      for (const change of nonSelectionChanges) {
        if (change.type === 'position' && change.dragging === false && change.position) {
          if (change.id.startsWith('image-')) {
            const imageId = change.id.replace('image-', '');
            onImagePositionChange(imageId, change.position);
          } else if (change.id.startsWith('section-')) {
            const sectionSlug = change.id.replace('section-', '');
            onSectionPositionChange(sectionSlug, change.position);
          } else if (change.id.startsWith('sticky-')) {
            const stickySlug = change.id.replace('sticky-', '');
            onStickyPositionChange(stickySlug, change.position);
          } else {
            onNotePositionChange(change.id, change.position);
          }
        }
      }
      return;
    }

    if (nodeDrag.shiftKeyRef.current) {
      const modifiedChanges = changes.map(change => {
        if (change.type === 'select') {
          const currentNode = nodes.find(n => n.id === change.id);
          if (currentNode?.selected && !change.selected) {
            const selectionChanges = changes.filter(c => c.type === 'select');
            if (selectionChanges.length > 1) {
              return { ...change, selected: true };
            }
          }
        }
        return change;
      });
      onNodesChange(modifiedChanges);
    } else {
      onNodesChange(changes);
    }

    for (const change of changes) {
      if (change.type === 'position' && change.dragging === false && change.position) {
        if (change.id.startsWith('image-')) {
          const imageId = change.id.replace('image-', '');
          onImagePositionChange(imageId, change.position);
        } else if (change.id.startsWith('section-')) {
          const sectionSlug = change.id.replace('section-', '');
          onSectionPositionChange(sectionSlug, change.position);
        } else if (change.id.startsWith('sticky-')) {
          const stickySlug = change.id.replace('sticky-', '');
          onStickyPositionChange(stickySlug, change.position);
        } else {
          onNotePositionChange(change.id, change.position);
        }
      }
    }
  }, [onNodesChange, onNotePositionChange, onImagePositionChange, onSectionPositionChange, onStickyPositionChange, nodes, isTouch, activeTool, nodeDrag.shiftKeyRef]);

  // Handle pane click
  const handlePaneClick = useCallback((event: React.MouseEvent) => {
    if (isPlacementMode && onPlacementClick) {
      const flowPosition = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const allNodes = getNodes();
      onPlacementClick(flowPosition, allNodes);
      return;
    }
    clearSelection();
  }, [isPlacementMode, onPlacementClick, screenToFlowPosition, clearSelection, getNodes]);

  // Handle node context menu
  const handleNodeContextMenu = useCallback((event: React.MouseEvent, node: Node<CanvasNodeData>) => {
    event.preventDefault();
    if (!node.selected) {
      setNodes(currentNodes =>
        currentNodes.map(n => ({ ...n, selected: n.id === node.id }))
      );
    }
    contextMenuHook.openContextMenu(event.clientX, event.clientY, 'node', node.id);
  }, [setNodes, contextMenuHook]);

  const handleSelectionContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    contextMenuHook.openContextMenu(event.clientX, event.clientY, 'node', undefined);
  }, [contextMenuHook]);

  // Paste target handler
  const handlePasteTargetPaste = useCallback((e: React.ClipboardEvent) => {
    if (!clipboard.pendingPasteRef.current) return;

    const items = e.clipboardData?.items;
    if (items) {
      for (const item of Array.from(items)) {
        if (item.type.startsWith('image/')) {
          e.preventDefault();
          const file = item.getAsFile();
          if (file) {
            const pastePosition = clipboard.contextMenuPositionRef.current;
            onImagePaste(file, pastePosition);
            clipboard.pendingPasteRef.current = false;
            setPasteInputPosition(prev => ({ ...prev, visible: false }));
            contextMenuHook.setContextMenu(null);
            return;
          }
        }
      }
    }

    clipboard.pendingPasteRef.current = false;
    setPasteInputPosition(prev => ({ ...prev, visible: false }));
  }, [onImagePaste, clipboard, contextMenuHook]);

  // Handle loader transition complete
  const handleLoaderTransitionComplete = useCallback(() => {
    setShowLoader(false);
    setIsEntering(true);
    // Remove entering class after animation completes
    setTimeout(() => setIsEntering(false), 400);
  }, []);

  const containerClasses = [
    styles['canvas-container'],
    isTouch && activeTool === 'pan' ? styles['pan-mode'] : '',
    isAnimating ? styles['animating'] : '',
    isEntering ? styles['canvas-container--entering'] : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={containerClasses} ref={touchGestures.setCanvasContainerRef}>
      {showLoader && (
        <CanvasLoader
          isLoading={loading}
          onTransitionComplete={handleLoaderTransitionComplete}
        />
      )}
      
      <ReactFlow
        nodes={nodes}
        edges={[]}
        onNodesChange={handleNodesChange}
        onNodeDragStart={nodeDrag.handleNodeDragStart}
        onNodeDrag={nodeDrag.handleNodeDrag}
        onNodeDragStop={nodeDrag.handleNodeDragStop}
        onPaneClick={handlePaneClick}
        onPaneContextMenu={contextMenuHook.handlePaneContextMenu}
        onNodeContextMenu={handleNodeContextMenu}
        onSelectionContextMenu={handleSelectionContextMenu}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        panOnScroll={true}
        panOnScrollMode={PanOnScrollMode.Free}
        panOnDrag={isTouch ? activeTool === 'pan' : false}
        panActivationKeyCode="Space"
        selectionOnDrag={isTouch ? activeTool === 'select' : true}
        selectionMode={SelectionMode.Partial}
        multiSelectionKeyCode="Shift"
        selectNodesOnDrag={false}
        nodesDraggable={!isTouch || activeTool === 'select'}
        elementsSelectable={!isTouch || activeTool === 'select'}
        nodesConnectable={false}
        deleteKeyCode={null}
        elevateNodesOnSelect={false}
      >
        <AdaptiveBackground />
        <Controls showInteractive={false} />
        <SnapGuides guides={guides} />
      </ReactFlow>

      <Dialog
        open={deleteDialogOpen}
        title={getDeleteDialogTitle()}
        message={getDeleteDialogMessage()}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
      />

      {contextMenuHook.contextMenu && (
        <ContextMenu
          x={contextMenuHook.contextMenu.x}
          y={contextMenuHook.contextMenu.y}
          items={contextMenuHook.contextMenuItems}
          onClose={contextMenuHook.handleContextMenuClose}
        />
      )}

      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleImageInputChange}
      />

      <input
        ref={pasteTargetRef}
        type="text"
        value=""
        readOnly
        style={{
          position: 'fixed',
          left: pasteInputPosition.visible ? `${pasteInputPosition.x - 50}px` : '-9999px',
          top: pasteInputPosition.visible ? `${pasteInputPosition.y - 20}px` : '-9999px',
          width: pasteInputPosition.visible ? '100px' : '1px',
          height: pasteInputPosition.visible ? '40px' : '1px',
          opacity: pasteInputPosition.visible ? 1 : 0,
          zIndex: pasteInputPosition.visible ? 10000 : -1,
          pointerEvents: pasteInputPosition.visible ? 'auto' : 'none',
          fontSize: '16px',
          background: pasteInputPosition.visible ? 'white' : 'transparent',
          border: pasteInputPosition.visible ? '2px solid #007AFF' : 'none',
          borderRadius: '8px',
          textAlign: 'center',
        }}
        onPaste={handlePasteTargetPaste}
        onBlur={() => {
          if (pasteInputPosition.visible) {
            setPasteInputPosition(prev => ({ ...prev, visible: false }));
            clipboard.pendingPasteRef.current = false;
          }
        }}
        aria-hidden="true"
        tabIndex={-1}
      />
    </div>
  );
}
