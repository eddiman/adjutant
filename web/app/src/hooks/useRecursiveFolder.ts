import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  RecursiveFolderEntry,
  RecursiveFolderListing,
  WebSidecar,
  Section,
  Sticky,
  StickyColor,
  Position,
  NoteFile,
  ItemMeta,
} from '../types';
import { layoutDirectoryTree, flattenDirLayouts } from '../utils/sectionPositioning.js';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function debounce<T extends (...args: any[]) => void>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

interface UseRecursiveFolderOptions {
  kb: string | null;
  path: string;
}

interface UseRecursiveFolderReturn {
  /** All notes (including from subdirectories), with preview and dirPath */
  allNotes: NoteFile[];
  /** Directory-backed sections derived from the filesystem */
  dirSections: Section[];
  /** User-created manual sections from the root sidecar */
  manualSections: Section[];
  /** All stickies from the root sidecar */
  stickies: Sticky[];
  /** Root sidecar metadata */
  meta: WebSidecar | null;
  /** Raw entries at root level (for sidebar) */
  rootEntries: RecursiveFolderEntry[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  /** Update item position — routes to the correct subfolder's sidecar */
  updateItemPosition: (itemName: string, position: Position, dirPath?: string) => void;
  /** Update section position/size (for manual sections) */
  updateSection: (id: string, updates: Partial<{ name: string; position: Position; width: number; height: number; color: string }>) => void;
  /** Update directory-section position/size (saved in root sidecar) */
  updateDirSectionPosition: (sectionId: string, position: Position) => void;
  updateDirSectionSize: (sectionId: string, width: number, height: number) => void;
  /** Create/delete manual sections */
  createSection: (input: { name?: string; position?: Position; width?: number; height?: number; color?: string }) => Promise<Section | null>;
  deleteSection: (id: string) => Promise<boolean>;
  /** Stickies */
  createSticky: (input: { text?: string; color?: StickyColor; position?: Position }) => Promise<Sticky | null>;
  updateSticky: (id: string, updates: Partial<{ text: string; color: StickyColor; position: Position }>) => void;
  deleteSticky: (id: string) => Promise<boolean>;
  /** Move a file/folder between directories */
  moveEntry: (sourcePath: string, destPath: string) => Promise<boolean>;
}

function sectionsFromMeta(meta: WebSidecar): Section[] {
  return Object.entries(meta.sections)
    .filter(([id]) => !id.startsWith('dirsection-'))
    .map(([id, s]) => ({ id, ...s }));
}

function stickiesFromMeta(meta: WebSidecar): Sticky[] {
  return Object.entries(meta.stickies).map(([id, s]) => ({ id, ...s }));
}

/**
 * Recursively collect all .md files from the tree, annotating with dirPath and preview.
 */
function collectNotes(
  entries: RecursiveFolderEntry[],
  kb: string,
  basePath: string,
  parentMeta: WebSidecar | null,
): NoteFile[] {
  const notes: NoteFile[] = [];

  for (const entry of entries) {
    if (entry.type === 'file' && entry.name.endsWith('.md')) {
      const itemMeta = parentMeta?.items[entry.name] || {};
      notes.push({
        filename: entry.name,
        path: entry.relativePath,
        kb,
        content: '',
        title: itemMeta.title || entry.name.replace(/\.md$/, ''),
        tags: itemMeta.tags || [],
        position: itemMeta.position,
        section: itemMeta.section,
        preview: entry.preview,
        dirPath: basePath,
        size: entry.size || 0,
        mtime: entry.mtime || '',
      });
    } else if (entry.type === 'folder' && entry.children) {
      notes.push(
        ...collectNotes(entry.children, kb, entry.relativePath, entry.meta || null),
      );
    }
  }

  return notes;
}

export function useRecursiveFolder(options: UseRecursiveFolderOptions): UseRecursiveFolderReturn {
  const { kb, path: folderPath } = options;
  const [data, setData] = useState<RecursiveFolderListing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTree = useCallback(async () => {
    if (!kb) {
      setData(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ kb, depth: '3' });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders/tree?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const listing: RecursiveFolderListing = await res.json();
      setData(listing);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch folder tree');
    } finally {
      setLoading(false);
    }
  }, [kb, folderPath]);

  useEffect(() => {
    fetchTree();
  }, [fetchTree]);

  // Build directory sections and note positions from the recursive tree
  const { dirSections, layoutNotePositions } = useMemo(() => {
    if (!data || !kb) return { dirSections: [] as Section[], layoutNotePositions: new Map<string, Position>() };

    const layouts = layoutDirectoryTree(data.entries, data.meta, kb, folderPath);
    const { sections, notePositions } = flattenDirLayouts(layouts);

    const now = new Date().toISOString();
    const dirSecs = sections.map(s => ({
      id: s.id,
      name: s.name,
      width: s.width,
      height: s.height,
      dirPath: s.dirPath,
      position: s.position,
      createdAt: now,
      updatedAt: now,
    }));

    return { dirSections: dirSecs, layoutNotePositions: notePositions };
  }, [data, kb, folderPath]);

  // Build notes from recursive data, applying layout positions for notes inside sections
  const allNotes = useMemo(() => {
    if (!data || !kb) return [];
    // Root-level notes (in the current path)
    const rootNotes = collectNotes(
      data.entries.filter(e => e.type === 'file'),
      kb,
      '',
      data.meta,
    );
    // Notes inside subdirectories
    const subNotes = collectNotes(
      data.entries.filter(e => e.type === 'folder'),
      kb,
      '',
      data.meta,
    );

    const allCollected = [...rootNotes, ...subNotes];

    // Apply layout-computed positions for notes inside directory sections
    // that don't already have a saved position in their sidecar.
    // Layout positions are absolute canvas coordinates.
    // Saved positions (from sidecar) are also absolute canvas coordinates.
    for (const note of allCollected) {
      if (note.dirPath && !note.position) {
        const layoutKey = `${note.dirPath}/${note.filename}`;
        const layoutPos = layoutNotePositions.get(layoutKey);
        if (layoutPos) {
          note.position = layoutPos;
        }
      }
    }

    return allCollected;
  }, [data, kb, layoutNotePositions, dirSections]);

  // Manual sections from root sidecar
  const manualSections = useMemo(() => {
    return data?.meta ? sectionsFromMeta(data.meta) : [];
  }, [data]);

  const stickies = useMemo(() => {
    return data?.meta ? stickiesFromMeta(data.meta) : [];
  }, [data]);

  // === Meta updates (debounced) — for root-level sidecar ===

  const pendingMetaRef = useRef<Partial<WebSidecar>>({});
  const debouncedSaveRef = useRef<ReturnType<typeof debounce> | null>(null);

  const saveMeta = useCallback(async () => {
    if (!kb) return;
    const pending = pendingMetaRef.current;
    pendingMetaRef.current = {};

    try {
      const params = new URLSearchParams({ kb });
      if (folderPath) params.set('path', folderPath);

      await fetch(`/api/folders/meta?${params}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pending),
      });
    } catch (err) {
      console.error('Failed to save folder meta:', err);
    }
  }, [kb, folderPath]);

  const getDebouncedSave = useCallback(() => {
    if (!debouncedSaveRef.current) {
      debouncedSaveRef.current = debounce(() => saveMeta(), 300);
    }
    return debouncedSaveRef.current;
  }, [saveMeta]);

  useEffect(() => {
    debouncedSaveRef.current = null;
  }, [kb, folderPath]);

  // === Position updates ===

  const updateItemPosition = useCallback((itemName: string, position: Position, dirPath?: string) => {
    if (!kb) return;

    if (dirPath) {
      // Update in subfolder's sidecar
      const params = new URLSearchParams({ kb });
      const subPath = folderPath ? `${folderPath}/${dirPath}` : dirPath;
      params.set('path', subPath);

      fetch(`/api/folders/meta?${params}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: { [itemName]: { position } } }),
      }).catch(err => console.error('Failed to update item position:', err));
    } else {
      // Update in root sidecar
      setData(prev => {
        if (!prev) return prev;
        const existing = prev.meta.items[itemName] || {};
        const merged = { ...existing, position };
        return {
          ...prev,
          meta: { ...prev.meta, items: { ...prev.meta.items, [itemName]: merged } },
        };
      });

      pendingMetaRef.current = {
        ...pendingMetaRef.current,
        items: {
          ...(pendingMetaRef.current.items || {}),
          [itemName]: { ...(pendingMetaRef.current.items?.[itemName] || {}), position },
        },
      };
      getDebouncedSave()();
    }
  }, [kb, folderPath, getDebouncedSave]);

  // === Dir section position/size updates (stored in root sidecar under sections key) ===

  const updateDirSectionPosition = useCallback((sectionId: string, position: Position) => {
    setData(prev => {
      if (!prev) return prev;
      const existing = prev.meta.sections[sectionId] || {
        name: '', width: 500, height: 400,
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(),
      };
      const updated = { ...existing, position, updatedAt: new Date().toISOString() };
      return {
        ...prev,
        meta: { ...prev.meta, sections: { ...prev.meta.sections, [sectionId]: updated } },
      };
    });

    pendingMetaRef.current = {
      ...pendingMetaRef.current,
      sections: {
        ...(pendingMetaRef.current.sections || {}),
        [sectionId]: {
          ...(pendingMetaRef.current.sections as Record<string, unknown>)?.[sectionId] as Record<string, unknown> || {},
          position,
          updatedAt: new Date().toISOString(),
        } as WebSidecar['sections'][string],
      },
    };
    getDebouncedSave()();
  }, [getDebouncedSave]);

  const updateDirSectionSize = useCallback((sectionId: string, width: number, height: number) => {
    setData(prev => {
      if (!prev) return prev;
      const existing = prev.meta.sections[sectionId];
      if (!existing) return prev;
      const updated = { ...existing, width, height, updatedAt: new Date().toISOString() };
      return {
        ...prev,
        meta: { ...prev.meta, sections: { ...prev.meta.sections, [sectionId]: updated } },
      };
    });

    pendingMetaRef.current = {
      ...pendingMetaRef.current,
      sections: {
        ...(pendingMetaRef.current.sections || {}),
        [sectionId]: {
          ...(pendingMetaRef.current.sections as Record<string, unknown>)?.[sectionId] as Record<string, unknown> || {},
          width,
          height,
          updatedAt: new Date().toISOString(),
        } as WebSidecar['sections'][string],
      },
    };
    getDebouncedSave()();
  }, [getDebouncedSave]);

  // === Manual section CRUD (same as useFolder) ===

  const updateSection = useCallback((id: string, updates: Partial<{ name: string; position: Position; width: number; height: number; color: string }>) => {
    setData(prev => {
      if (!prev || !prev.meta.sections[id]) return prev;
      const existing = prev.meta.sections[id];
      const updated = { ...existing, ...updates, updatedAt: new Date().toISOString() };
      return {
        ...prev,
        meta: { ...prev.meta, sections: { ...prev.meta.sections, [id]: updated } },
      };
    });

    pendingMetaRef.current = {
      ...pendingMetaRef.current,
      sections: {
        ...(pendingMetaRef.current.sections || {}),
        [id]: {
          ...(pendingMetaRef.current.sections as Record<string, unknown>)?.[id] as Record<string, unknown> || {},
          ...updates,
          updatedAt: new Date().toISOString(),
        } as WebSidecar['sections'][string],
      },
    };
    getDebouncedSave()();
  }, [getDebouncedSave]);

  const createSection = useCallback(async (input: { name?: string; position?: Position; width?: number; height?: number; color?: string }): Promise<Section | null> => {
    if (!kb) return null;
    try {
      const params = new URLSearchParams({ kb });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders/sections?${params}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      const section: Section = { id: result.id, ...result.section };

      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          meta: { ...prev.meta, sections: { ...prev.meta.sections, [result.id]: result.section } },
        };
      });

      return section;
    } catch (err) {
      console.error('Failed to create section:', err);
      return null;
    }
  }, [kb, folderPath]);

  const deleteSection = useCallback(async (id: string): Promise<boolean> => {
    if (!kb) return false;

    // Don't allow deleting directory sections
    if (id.startsWith('dirsection-')) return false;

    setData(prev => {
      if (!prev) return prev;
      const { [id]: _, ...rest } = prev.meta.sections;
      return { ...prev, meta: { ...prev.meta, sections: rest } };
    });

    try {
      const params = new URLSearchParams({ kb, id });
      if (folderPath) params.set('path', folderPath);
      const res = await fetch(`/api/folders/sections?${params}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
      return true;
    } catch (err) {
      console.error('Failed to delete section:', err);
      await fetchTree();
      return false;
    }
  }, [kb, folderPath, fetchTree]);

  // === Stickies ===

  const createSticky = useCallback(async (input: { text?: string; color?: StickyColor; position?: Position }): Promise<Sticky | null> => {
    if (!kb) return null;
    try {
      const params = new URLSearchParams({ kb });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders/stickies?${params}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json();
      const sticky: Sticky = { id: result.id, ...result.sticky };

      setData(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          meta: { ...prev.meta, stickies: { ...prev.meta.stickies, [result.id]: result.sticky } },
        };
      });

      return sticky;
    } catch (err) {
      console.error('Failed to create sticky:', err);
      return null;
    }
  }, [kb, folderPath]);

  const updateSticky = useCallback((id: string, updates: Partial<{ text: string; color: StickyColor; position: Position }>) => {
    setData(prev => {
      if (!prev || !prev.meta.stickies[id]) return prev;
      const existing = prev.meta.stickies[id];
      const updated = { ...existing, ...updates, updatedAt: new Date().toISOString() };
      return {
        ...prev,
        meta: { ...prev.meta, stickies: { ...prev.meta.stickies, [id]: updated } },
      };
    });

    pendingMetaRef.current = {
      ...pendingMetaRef.current,
      stickies: {
        ...(pendingMetaRef.current.stickies || {}),
        [id]: {
          ...(pendingMetaRef.current.stickies as Record<string, unknown>)?.[id] as Record<string, unknown> || {},
          ...updates,
          updatedAt: new Date().toISOString(),
        } as WebSidecar['stickies'][string],
      },
    };
    getDebouncedSave()();
  }, [getDebouncedSave]);

  const deleteSticky = useCallback(async (id: string): Promise<boolean> => {
    if (!kb) return false;

    setData(prev => {
      if (!prev) return prev;
      const { [id]: _, ...rest } = prev.meta.stickies;
      return { ...prev, meta: { ...prev.meta, stickies: rest } };
    });

    try {
      const params = new URLSearchParams({ kb, id });
      if (folderPath) params.set('path', folderPath);
      const res = await fetch(`/api/folders/stickies?${params}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
      return true;
    } catch (err) {
      console.error('Failed to delete sticky:', err);
      await fetchTree();
      return false;
    }
  }, [kb, folderPath, fetchTree]);

  // === Move entry ===

  const moveEntry = useCallback(async (sourcePath: string, destPath: string): Promise<boolean> => {
    if (!kb) return false;

    try {
      const res = await fetch('/api/folders/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kb, sourcePath, destPath }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchTree(); // Refetch to get updated state
      return true;
    } catch (err) {
      console.error('Failed to move entry:', err);
      return false;
    }
  }, [kb, fetchTree]);

  return {
    allNotes,
    dirSections,
    manualSections,
    stickies,
    meta: data?.meta || null,
    rootEntries: data?.entries || [],
    loading,
    error,
    refetch: fetchTree,
    updateItemPosition,
    updateSection,
    updateDirSectionPosition,
    updateDirSectionSize,
    createSection,
    deleteSection,
    createSticky,
    updateSticky,
    deleteSticky,
    moveEntry,
  };
}
