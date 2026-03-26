import { useCallback, useEffect, useState } from 'react';
import type { KbMeta } from '../types';

interface UseKbsReturn {
  kbs: KbMeta[];
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useKbs(): UseKbsReturn {
  const [kbs, setKbs] = useState<KbMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchKbs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/kbs');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setKbs(data.kbs || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch knowledge bases');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKbs();
  }, [fetchKbs]);

  return { kbs, loading, error, refetch: fetchKbs };
}
