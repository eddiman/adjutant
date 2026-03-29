import { useState, useCallback, useEffect } from 'react';
import type { DirectoryEntry, ExplorerRoots, KbRootValidation } from '../types';

interface UseExplorerOptions {
  /** Auto-fetch roots on mount */
  autoLoad?: boolean;
}

export function useExplorer(options: UseExplorerOptions = { autoLoad: true }) {
  const [roots, setRoots] = useState<ExplorerRoots | null>(null);
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [currentPath, setCurrentPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRoots = useCallback(async () => {
    try {
      const res = await fetch('/api/explorer/roots');
      if (!res.ok) throw new Error('Failed to fetch roots');
      const data: ExplorerRoots = await res.json();
      setRoots(data);
      return data;
    } catch (err) {
      setError('Failed to connect to server');
      return null;
    }
  }, []);

  const navigateTo = useCallback(async (absolutePath: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/explorer/list?path=${encodeURIComponent(absolutePath)}`);
      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: 'Request failed' }));
        setError(data.error || 'Failed to list directory');
        return;
      }
      const data = await res.json();
      setEntries(data.entries);
      setCurrentPath(absolutePath);
    } catch {
      setError('Failed to connect to server');
    } finally {
      setLoading(false);
    }
  }, []);

  const navigateUp = useCallback(() => {
    if (!currentPath) return;
    // On Unix, parent of '/' is '/', on Windows parent of 'C:\' is 'C:\'
    const parent = currentPath.replace(/[/\\][^/\\]*$/, '') || '/';
    if (parent !== currentPath) {
      navigateTo(parent);
    }
  }, [currentPath, navigateTo]);

  const validateKbRoot = useCallback(async (absolutePath: string): Promise<KbRootValidation> => {
    try {
      const res = await fetch(`/api/explorer/validate?path=${encodeURIComponent(absolutePath)}`);
      if (!res.ok) return { valid: false, kbCount: 0, kbNames: [] };
      return await res.json();
    } catch {
      return { valid: false, kbCount: 0, kbNames: [] };
    }
  }, []);

  useEffect(() => {
    if (options.autoLoad) {
      fetchRoots();
    }
  }, [options.autoLoad, fetchRoots]);

  return {
    roots,
    entries,
    currentPath,
    loading,
    error,
    fetchRoots,
    navigateTo,
    navigateUp,
    validateKbRoot,
  };
}
