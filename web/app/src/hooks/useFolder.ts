import { useCallback, useEffect, useState, useRef } from 'react';
import type {
  FolderListing,
  FolderEntry,
  WebSidecar,
  Section,
  Sticky,
  StickyColor,
  Position,
  ItemMeta,
} from '../types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function debounce<T extends (...args: any[]) => void>(fn: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

interface UseFolderOptions {
  kb: string | null;
  path: string;
}

interface UseFolderReturn {
  entries: FolderEntry[];
  meta: WebSidecar | null;
  sections: Section[];
  stickies: Sticky[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  updateItemMeta: (itemName: string, updates: Partial<ItemMeta>) => void;
  updateItemPosition: (itemName: string, position: Position) => void;
  createSection: (input: { name?: string; position?: Position; width?: number; height?: number; color?: string }) => Promise<Section | null>;
  updateSection: (id: string, updates: Partial<{ name: string; position: Position; width: number; height: number; color: string }>) => void;
  deleteSection: (id: string) => Promise<boolean>;
  createSticky: (input: { text?: string; color?: StickyColor; position?: Position }) => Promise<Sticky | null>;
  updateSticky: (id: string, updates: Partial<{ text: string; color: StickyColor; position: Position }>) => void;
  deleteSticky: (id: string) => Promise<boolean>;
}

function sectionsFromMeta(meta: WebSidecar): Section[] {
  return Object.entries(meta.sections).map(([id, s]) => ({
    id, ...s, width: s.width ?? 500, height: s.height ?? 400,
  }));
}

function stickiesFromMeta(meta: WebSidecar): Sticky[] {
  return Object.entries(meta.stickies).map(([id, s]) => ({ id, ...s }));
}

export function useFolder(options: UseFolderOptions): UseFolderReturn {
  const { kb, path: folderPath } = options;
  const [entries, setEntries] = useState<FolderEntry[]>([]);
  const [meta, setMeta] = useState<WebSidecar | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchFolder = useCallback(async () => {
    if (!kb) {
      setEntries([]);
      setMeta(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ kb });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: FolderListing = await res.json();
      setEntries(data.entries);
      setMeta(data.meta);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch folder');
    } finally {
      setLoading(false);
    }
  }, [kb, folderPath]);

  useEffect(() => {
    fetchFolder();
  }, [fetchFolder]);

  // === Meta updates (debounced) ===

  const pendingMetaRef = useRef<Partial<WebSidecar>>({});
  const debouncedSaveMetaRef = useRef<ReturnType<typeof debounce> | null>(null);

  const saveMeta = useCallback(async () => {
    if (!kb) return;
    const pending = pendingMetaRef.current;
    pendingMetaRef.current = {};

    try {
      const params = new URLSearchParams({ kb });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders/meta?${params}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pending),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated: WebSidecar = await res.json();
      setMeta(updated);
    } catch (err) {
      console.error('Failed to save folder meta:', err);
    }
  }, [kb, folderPath]);

  const getDebouncedSave = useCallback(() => {
    if (!debouncedSaveMetaRef.current) {
      debouncedSaveMetaRef.current = debounce(() => saveMeta(), 300);
    }
    return debouncedSaveMetaRef.current;
  }, [saveMeta]);

  // Reset debounce when kb/path changes
  useEffect(() => {
    debouncedSaveMetaRef.current = null;
  }, [kb, folderPath]);

  const updateItemMeta = useCallback((itemName: string, updates: Partial<ItemMeta>) => {
    setMeta(prev => {
      if (!prev) return prev;
      const existing = prev.items[itemName] || {};
      const merged = { ...existing, ...updates };
      const newItems = { ...prev.items, [itemName]: merged };
      const newMeta = { ...prev, items: newItems };

      pendingMetaRef.current = {
        ...pendingMetaRef.current,
        items: { ...(pendingMetaRef.current.items || {}), [itemName]: merged },
      };
      getDebouncedSave()();

      return newMeta;
    });
  }, [getDebouncedSave]);

  const updateItemPosition = useCallback((itemName: string, position: Position) => {
    updateItemMeta(itemName, { position });
  }, [updateItemMeta]);

  // === Sections ===

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
      const data = await res.json();
      const section: Section = { id: data.id, ...data.section };

      setMeta(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          sections: { ...prev.sections, [data.id]: data.section },
        };
      });

      return section;
    } catch (err) {
      console.error('Failed to create section:', err);
      return null;
    }
  }, [kb, folderPath]);

  const updateSection = useCallback((id: string, updates: Partial<{ name: string; position: Position; width: number; height: number; color: string }>) => {
    setMeta(prev => {
      if (!prev || !prev.sections[id]) return prev;
      const existing = prev.sections[id];
      const updated = { ...existing, ...updates, updatedAt: new Date().toISOString() };
      const newSections = { ...prev.sections, [id]: updated };
      const newMeta = { ...prev, sections: newSections };

      pendingMetaRef.current = {
        ...pendingMetaRef.current,
        sections: { ...(pendingMetaRef.current.sections || {}), [id]: updated },
      };
      getDebouncedSave()();

      return newMeta;
    });
  }, [getDebouncedSave]);

  const deleteSection = useCallback(async (id: string): Promise<boolean> => {
    if (!kb) return false;

    // Optimistic delete
    setMeta(prev => {
      if (!prev) return prev;
      const { [id]: _, ...rest } = prev.sections;
      return { ...prev, sections: rest };
    });

    try {
      const params = new URLSearchParams({ kb, id });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders/sections?${params}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
      return true;
    } catch (err) {
      console.error('Failed to delete section:', err);
      await fetchFolder();
      return false;
    }
  }, [kb, folderPath, fetchFolder]);

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
      const data = await res.json();
      const sticky: Sticky = { id: data.id, ...data.sticky };

      setMeta(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          stickies: { ...prev.stickies, [data.id]: data.sticky },
        };
      });

      return sticky;
    } catch (err) {
      console.error('Failed to create sticky:', err);
      return null;
    }
  }, [kb, folderPath]);

  const updateSticky = useCallback((id: string, updates: Partial<{ text: string; color: StickyColor; position: Position }>) => {
    setMeta(prev => {
      if (!prev || !prev.stickies[id]) return prev;
      const existing = prev.stickies[id];
      const updated = { ...existing, ...updates, updatedAt: new Date().toISOString() };
      const newStickies = { ...prev.stickies, [id]: updated };
      const newMeta = { ...prev, stickies: newStickies };

      pendingMetaRef.current = {
        ...pendingMetaRef.current,
        stickies: { ...(pendingMetaRef.current.stickies || {}), [id]: updated },
      };
      getDebouncedSave()();

      return newMeta;
    });
  }, [getDebouncedSave]);

  const deleteSticky = useCallback(async (id: string): Promise<boolean> => {
    if (!kb) return false;

    setMeta(prev => {
      if (!prev) return prev;
      const { [id]: _, ...rest } = prev.stickies;
      return { ...prev, stickies: rest };
    });

    try {
      const params = new URLSearchParams({ kb, id });
      if (folderPath) params.set('path', folderPath);

      const res = await fetch(`/api/folders/stickies?${params}`, { method: 'DELETE' });
      if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
      return true;
    } catch (err) {
      console.error('Failed to delete sticky:', err);
      await fetchFolder();
      return false;
    }
  }, [kb, folderPath, fetchFolder]);

  const sections = meta ? sectionsFromMeta(meta) : [];
  const stickies = meta ? stickiesFromMeta(meta) : [];

  return {
    entries,
    meta,
    sections,
    stickies,
    loading,
    error,
    refetch: fetchFolder,
    updateItemMeta,
    updateItemPosition,
    createSection,
    updateSection,
    deleteSection,
    createSticky,
    updateSticky,
    deleteSticky,
  };
}
