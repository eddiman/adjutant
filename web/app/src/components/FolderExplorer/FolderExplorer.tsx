import { useEffect, useCallback, useState } from 'react';
import { useExplorer } from '../../hooks/useExplorer';
import type { DirectoryEntry, KbRootValidation } from '../../types';
import styles from './FolderExplorer.module.css';

interface FolderExplorerProps {
  open: boolean;
  onSelect: (path: string) => void;
  onClose: () => void;
  initialPath?: string;
}

export function FolderExplorer({ open, onSelect, onClose, initialPath }: FolderExplorerProps) {
  const {
    roots,
    entries,
    currentPath,
    loading,
    error,
    navigateTo,
    navigateUp,
    validateKbRoot,
  } = useExplorer({ autoLoad: open });

  const [selected, setSelected] = useState<string | null>(null);
  const [validation, setValidation] = useState<KbRootValidation | null>(null);
  const [validating, setValidating] = useState(false);

  // Navigate to initial path or home on open
  useEffect(() => {
    if (open && roots && !currentPath) {
      const startPath = initialPath || roots.current || roots.home;
      navigateTo(startPath);
    }
  }, [open, roots, currentPath, initialPath, navigateTo]);

  // Validate when selection changes
  useEffect(() => {
    if (!selected) {
      setValidation(null);
      return;
    }
    let cancelled = false;
    setValidating(true);
    validateKbRoot(selected).then(v => {
      if (!cancelled) {
        setValidation(v);
        setValidating(false);
      }
    });
    return () => { cancelled = true; };
  }, [selected, validateKbRoot]);

  // Also validate current path (for "select current directory")
  useEffect(() => {
    if (!currentPath) return;
    // Auto-select current directory
    setSelected(currentPath);
  }, [currentPath]);

  // Keyboard handling
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    if (open) {
      window.addEventListener('keydown', handleKeyDown, { capture: true });
      return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
    }
  }, [open, handleKeyDown]);

  const handleEntryClick = useCallback((entry: DirectoryEntry) => {
    setSelected(entry.path);
  }, []);

  const handleEntryDoubleClick = useCallback((entry: DirectoryEntry) => {
    navigateTo(entry.path);
  }, [navigateTo]);

  const handleSelect = useCallback(() => {
    if (selected) {
      onSelect(selected);
    }
  }, [selected, onSelect]);

  if (!open) return null;

  // Build breadcrumb segments from current path
  const breadcrumbSegments = currentPath
    ? currentPath.split('/').reduce<{ label: string; path: string }[]>((acc, seg, i) => {
        if (i === 0) {
          acc.push({ label: '/', path: '/' });
        } else if (seg) {
          const prevPath = acc[acc.length - 1]?.path || '';
          acc.push({ label: seg, path: prevPath === '/' ? `/${seg}` : `${prevPath}/${seg}` });
        }
        return acc;
      }, [])
    : [];

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.explorer} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <h3 className={styles.title}>Browse Server Directories</h3>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 4L4 12M4 4l8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Quick roots */}
        {roots && (
          <div className={styles.roots}>
            {roots.roots.map(r => (
              <button
                key={r.path}
                className={`${styles.rootBtn} ${currentPath === r.path ? styles.rootBtnActive : ''}`}
                onClick={() => navigateTo(r.path)}
              >
                {r.label}
              </button>
            ))}
            {roots.current && !roots.roots.some(r => r.path === roots.current) && (
              <button
                className={`${styles.rootBtn} ${currentPath === roots.current ? styles.rootBtnActive : ''}`}
                onClick={() => navigateTo(roots.current!)}
              >
                Current KB Root
              </button>
            )}
          </div>
        )}

        {/* Breadcrumb */}
        {currentPath && (
          <div className={styles.breadcrumb}>
            {currentPath !== '/' && (
              <button className={styles.breadcrumbSeg} onClick={navigateUp} title="Go up">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M15 18l-6-6 6-6"/>
                </svg>
              </button>
            )}
            {breadcrumbSegments.map((seg, i) => (
              <span key={seg.path} style={{ display: 'contents' }}>
                {i > 0 && <span className={styles.breadcrumbSep}>/</span>}
                <button
                  className={styles.breadcrumbSeg}
                  onClick={() => navigateTo(seg.path)}
                >
                  {seg.label === '/' ? '/' : seg.label}
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Directory listing */}
        <div className={styles.listing}>
          {loading ? (
            <div className={styles.loading}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles.spinner}>
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
              </svg>
            </div>
          ) : error ? (
            <div className={styles.error}>{error}</div>
          ) : entries.length === 0 ? (
            <div className={styles.listingEmpty}>No subdirectories</div>
          ) : (
            entries.map(entry => (
              <button
                key={entry.path}
                className={`${styles.dirEntry} ${selected === entry.path ? styles.dirEntrySelected : ''}`}
                onClick={() => handleEntryClick(entry)}
                onDoubleClick={() => handleEntryDoubleClick(entry)}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles.dirIcon}>
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                <span className={styles.dirName}>{entry.name}</span>
                {entry.hasChildren && (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles.dirArrow}>
                    <path d="M9 18l6-6-6-6"/>
                  </svg>
                )}
              </button>
            ))
          )}
        </div>

        {/* Footer with selection & validate */}
        <div className={styles.footer}>
          <span className={styles.selectedPath}>
            {selected || 'No directory selected'}
          </span>
          {selected && (
            <span className={`${styles.validation} ${validation?.valid ? styles.validationValid : styles.validationInvalid}`}>
              {validating
                ? 'Checking...'
                : validation?.valid
                  ? `${validation.kbCount} KB${validation.kbCount !== 1 ? 's' : ''} found`
                  : 'No KBs found'}
            </span>
          )}
          <button
            className={styles.selectBtn}
            onClick={handleSelect}
            disabled={!selected}
          >
            Select
          </button>
        </div>
      </div>
    </div>
  );
}

export default FolderExplorer;
