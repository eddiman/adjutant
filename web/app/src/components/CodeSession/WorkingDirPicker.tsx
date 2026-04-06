/**
 * Working directory picker for code sessions.
 *
 * Thin wrapper around the existing FolderExplorer component,
 * stripping the KB validation UI and changing the title.
 */

import { useCallback } from 'react';
import { useExplorer } from '../../hooks/useExplorer';
import type { DirectoryEntry } from '../../types';
import { useEffect, useState } from 'react';

interface WorkingDirPickerProps {
  open: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export function WorkingDirPicker({ open, onSelect, onClose }: WorkingDirPickerProps) {
  const {
    roots,
    entries,
    currentPath,
    loading,
    error,
    navigateTo,
    navigateUp,
  } = useExplorer({ autoLoad: open });

  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (open && roots && !currentPath) {
      navigateTo(roots.current || roots.home);
    }
  }, [open, roots, currentPath, navigateTo]);

  useEffect(() => {
    if (currentPath) setSelected(currentPath);
  }, [currentPath]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } };
    window.addEventListener('keydown', handler, { capture: true });
    return () => window.removeEventListener('keydown', handler, { capture: true });
  }, [open, onClose]);

  const handleEntryClick = useCallback((entry: DirectoryEntry) => {
    setSelected(entry.path);
  }, []);

  const handleEntryDoubleClick = useCallback((entry: DirectoryEntry) => {
    navigateTo(entry.path);
  }, [navigateTo]);

  const handleSelect = useCallback(() => {
    if (selected) onSelect(selected);
  }, [selected, onSelect]);

  if (!open) return null;

  const breadcrumbSegments = currentPath
    ? currentPath.split('/').reduce<{ label: string; path: string }[]>((acc, seg, i) => {
        if (i === 0) acc.push({ label: '/', path: '/' });
        else if (seg) {
          const prevPath = acc[acc.length - 1]?.path || '';
          acc.push({ label: seg, path: prevPath === '/' ? `/${seg}` : `${prevPath}/${seg}` });
        }
        return acc;
      }, [])
    : [];

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--cs-card)', border: '1px solid var(--cs-border)',
          borderRadius: '0.5rem', width: '32rem', maxHeight: '28rem',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        <div style={{
          padding: '0.75rem 1rem', borderBottom: '1px solid var(--cs-border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <h3 style={{ margin: 0, fontSize: '0.875rem', color: 'var(--cs-text)' }}>Select Working Directory</h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--cs-text-muted)', cursor: 'pointer', fontSize: '1rem' }}
          >
            x
          </button>
        </div>

        {roots && (
          <div style={{ display: 'flex', gap: '0.375rem', padding: '0.5rem 1rem', flexWrap: 'wrap' }}>
            {roots.roots.map(r => (
              <button
                key={r.path}
                onClick={() => navigateTo(r.path)}
                style={{
                  padding: '0.25rem 0.5rem', fontSize: '0.75rem', borderRadius: '0.25rem',
                  border: '1px solid var(--cs-border)', cursor: 'pointer',
                  background: currentPath === r.path ? 'rgba(124,92,191,0.15)' : 'none',
                  color: 'var(--cs-text-secondary)', fontFamily: 'inherit',
                }}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}

        {currentPath && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.25rem 1rem', fontSize: '0.75rem' }}>
            {currentPath !== '/' && (
              <button onClick={navigateUp} style={{ background: 'none', border: 'none', color: 'var(--cs-text-secondary)', cursor: 'pointer', padding: '0.125rem' }}>
                ..
              </button>
            )}
            {breadcrumbSegments.map((seg, i) => (
              <span key={seg.path} style={{ display: 'contents' }}>
                {i > 0 && <span style={{ color: 'var(--cs-text-muted)' }}>/</span>}
                <button
                  onClick={() => navigateTo(seg.path)}
                  style={{ background: 'none', border: 'none', color: 'var(--cs-text-secondary)', cursor: 'pointer', padding: '0.125rem', fontFamily: 'inherit', fontSize: 'inherit' }}
                >
                  {seg.label === '/' ? '/' : seg.label}
                </button>
              </span>
            ))}
          </div>
        )}

        <div style={{ flex: 1, overflowY: 'auto', padding: '0.25rem 0' }}>
          {loading ? (
            <p style={{ padding: '1rem', textAlign: 'center', color: 'var(--cs-text-muted)', fontSize: '0.8125rem' }}>Loading...</p>
          ) : error ? (
            <p style={{ padding: '1rem', textAlign: 'center', color: '#f56c6c', fontSize: '0.8125rem' }}>{error}</p>
          ) : entries.length === 0 ? (
            <p style={{ padding: '1rem', textAlign: 'center', color: 'var(--cs-text-muted)', fontSize: '0.8125rem' }}>No subdirectories</p>
          ) : (
            entries.map(entry => (
              <button
                key={entry.path}
                onClick={() => handleEntryClick(entry)}
                onDoubleClick={() => handleEntryDoubleClick(entry)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  width: '100%', padding: '0.375rem 1rem', background: selected === entry.path ? 'rgba(124,92,191,0.1)' : 'none',
                  border: 'none', cursor: 'pointer', color: 'var(--cs-text)', textAlign: 'left',
                  fontFamily: 'inherit', fontSize: '0.8125rem',
                }}
              >
                <span>📁</span>
                <span style={{ flex: 1 }}>{entry.name}</span>
                {entry.hasChildren && <span style={{ color: 'var(--cs-text-muted)' }}>›</span>}
              </button>
            ))
          )}
        </div>

        <div style={{
          padding: '0.625rem 1rem', borderTop: '1px solid var(--cs-border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--cs-text-secondary)', fontFamily: "'SF Mono', monospace" }}>
            {selected || 'No directory selected'}
          </span>
          <button
            onClick={handleSelect}
            disabled={!selected}
            style={{
              background: selected ? 'var(--cs-accent)' : 'var(--cs-border)',
              color: '#fff', border: 'none', padding: '0.375rem 1rem',
              borderRadius: '0.25rem', cursor: selected ? 'pointer' : 'not-allowed',
              fontSize: '0.8125rem', fontWeight: 500,
            }}
          >
            Select
          </button>
        </div>
      </div>
    </div>
  );
}
