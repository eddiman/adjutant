/**
 * Working directory picker for code sessions.
 */

import { useCallback, useEffect, useState } from 'react';
import { useExplorer } from '../../hooks/useExplorer';
import type { DirectoryEntry } from '../../types';
import { Modal } from '../ui';
import styles from './WorkingDirPicker.module.css';

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

  const footerJSX = (
    <>
      <span className={styles.footerPath}>
        {selected || 'No directory selected'}
      </span>
      <button
        className={styles.selectBtn}
        onClick={handleSelect}
        disabled={!selected}
      >
        Select
      </button>
    </>
  );

  return (
    <Modal open={open} onClose={onClose} title="Select Working Directory" width="32rem" footer={footerJSX}>
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
        </div>
      )}

      {currentPath && (
        <div className={styles.breadcrumb}>
          {currentPath !== '/' && (
            <button className={styles.breadcrumbBtn} onClick={navigateUp}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
          )}
          {breadcrumbSegments.map((seg, i) => (
            <span key={seg.path} style={{ display: 'contents' }}>
              {i > 0 && <span className={styles.breadcrumbSep}>/</span>}
              <button className={styles.breadcrumbBtn} onClick={() => navigateTo(seg.path)}>
                {seg.label === '/' ? '/' : seg.label}
              </button>
            </span>
          ))}
        </div>
      )}

      <div className={styles.listing}>
        {loading ? (
          <p className={styles.emptyMsg}>Loading...</p>
        ) : error ? (
          <p className={styles.errorMsg}>{error}</p>
        ) : entries.length === 0 ? (
          <p className={styles.emptyMsg}>No subdirectories</p>
        ) : (
          entries.map(entry => (
            <button
              key={entry.path}
              className={`${styles.entry} ${selected === entry.path ? styles.entrySelected : ''}`}
              onClick={() => handleEntryClick(entry)}
              onDoubleClick={() => handleEntryDoubleClick(entry)}
            >
              <span className={styles.entryIcon}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
                </svg>
              </span>
              <span className={styles.entryName}>{entry.name}</span>
              {entry.hasChildren && (
                <span className={styles.entryChevron}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </span>
              )}
            </button>
          ))
        )}
      </div>
    </Modal>
  );
}
