import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { isMobileViewport } from '../../utils/platform.js';
import type { KbMeta, RecursiveFolderEntry } from '../../types';
import styles from './Sidebar.module.css';

interface SidebarProps {
  open: boolean;
  onToggle: () => void;
  kbs: KbMeta[];
  currentKb: string | null;
  currentPath: string;
  entries: RecursiveFolderEntry[];
  onKbSelect: (kb: string | null) => void;
  onFolderFocus?: (folderName: string) => void;
  onNoteOpen: (notePath: string) => void;
  onSettingsClick: () => void;
  onNavigateToFolder: (kb: string, path: string) => void;
  loading?: boolean;
  highlightedDirPath?: string | null;
}

export function Sidebar({
  open,
  onToggle,
  kbs,
  currentKb,
  currentPath,
  entries,
  onKbSelect,
  onFolderFocus,
  onNoteOpen,
  onSettingsClick,
  onNavigateToFolder,
  loading = false,
  highlightedDirPath,
}: SidebarProps) {
  const location = useLocation();
  const isAdjutantPage = location.pathname === '/adjutant';
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());

  // Reset expanded folders when KB changes
  useEffect(() => {
    setExpandedFolders(new Set());
  }, [currentKb]);

  const handleKbClick = useCallback((kbName: string) => {
    onKbSelect(kbName);
    if (isMobileViewport() && open) onToggle();
  }, [onKbSelect, open, onToggle]);

  const toggleFolder = useCallback((folderPath: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(folderPath)) {
        next.delete(folderPath);
      } else {
        next.add(folderPath);
      }
      return next;
    });
  }, []);

  const handleFolderFocusClick = useCallback((e: React.MouseEvent, folderName: string) => {
    e.stopPropagation();
    if (onFolderFocus) onFolderFocus(folderName);
  }, [onFolderFocus]);

  const handleNoteClick = useCallback((notePath: string) => {
    onNoteOpen(notePath);
    if (isMobileViewport() && open) onToggle();
  }, [onNoteOpen, open, onToggle]);

  const handleSettingsClick = useCallback(() => {
    onSettingsClick();
    if (isMobileViewport() && open) onToggle();
  }, [onSettingsClick, open, onToggle]);

  const handleBreadcrumbClick = useCallback((index: number) => {
    if (!currentKb) return;
    const parts = currentPath.split('/').filter(Boolean);
    const newPath = parts.slice(0, index).join('/');
    onNavigateToFolder(currentKb, newPath);
  }, [currentKb, currentPath, onNavigateToFolder]);

  const handleHomeClick = useCallback(() => {
    onKbSelect(null);
    if (isMobileViewport() && open) onToggle();
  }, [onKbSelect, open, onToggle]);

  // Build breadcrumb trail
  const breadcrumbs = currentPath ? currentPath.split('/').filter(Boolean) : [];

  const renderEntryTree = (entryList: RecursiveFolderEntry[], depth: number) => {
    return entryList.map(entry => {
      const entryPath = entry.relativePath || entry.name;

      if (entry.type === 'folder') {
        const isExpanded = expandedFolders.has(entryPath);
        const isHighlighted = highlightedDirPath === (currentPath ? `${currentPath}/${entryPath}` : entryPath);
        return (
          <div key={entryPath}>
            <div
              className={`${styles['sidebar-entry']} ${isHighlighted ? styles['sidebar-entry-highlighted'] : ''}`}
              style={depth > 0 ? { paddingLeft: `${14 + depth * 12}px` } : undefined}
              onClick={() => toggleFolder(entryPath)}
              role="button"
              tabIndex={0}
            >
              <svg
                width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                style={{ transform: isExpanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}
              >
                <polyline points="9 18 15 12 9 6"/>
              </svg>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
              <span className={styles['sidebar-entry-text']}>{entry.name}</span>
              {onFolderFocus && (
                <button
                  className={styles['sidebar-entry-focus']}
                  onClick={(e) => handleFolderFocusClick(e, entryPath)}
                  title="Focus on canvas"
                  aria-label={`Focus ${entry.name} on canvas`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                </button>
              )}
            </div>
            {isExpanded && entry.children && (
              <div>{renderEntryTree(entry.children, depth + 1)}</div>
            )}
          </div>
        );
      }

      // File entry
      if (!entry.name.endsWith('.md')) return null;
      return (
        <div
          key={entryPath}
          className={styles['sidebar-entry']}
          style={depth > 0 ? { paddingLeft: `${14 + depth * 12}px` } : undefined}
          onClick={() => handleNoteClick(entryPath)}
          role="button"
          tabIndex={0}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <span className={styles['sidebar-entry-text']}>{entry.name}</span>
        </div>
      );
    });
  };

  return (
    <aside className={`${styles.sidebar} ${open ? styles.open : ''}`}>
      {/* Toggle button */}
      <button 
        className={styles['sidebar-toggle-btn']}
        onClick={onToggle}
        aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
      >
        <svg 
          className={styles['sidebar-toggle-icon']}
          width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
        >
          {open ? (
            <>
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <rect x="3" y="3" width="6" height="18" rx="1" fill="currentColor" stroke="none"/>
              <path d="M9 3v18"/>
            </>
          ) : (
            <>
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <path d="M9 3v18"/>
            </>
          )}
        </svg>
      </button>

      {/* Sidebar content */}
      <div className={styles['sidebar-content']}>
        <div className={styles['sidebar-header']}>
          <h2 className={styles['sidebar-title']}>Adjutant Web</h2>
        </div>

        <nav className={styles['sidebar-nav']}>
          {/* Home link */}
          <button
            className={`${styles['sidebar-item']} ${!currentKb && !isAdjutantPage ? styles.active : ''}`}
            onClick={handleHomeClick}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
              <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            <span className={styles['sidebar-item-text']}>Home</span>
          </button>

          {/* Adjutant Dashboard link */}
          <Link
            to="/adjutant"
            className={`${styles['sidebar-item']} ${isAdjutantPage ? styles.active : ''}`}
            onClick={() => { if (isMobileViewport() && open) onToggle(); }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 1v6m0 6v6m8.66-15L17 7.5M7 16.5l-3.66 4.5M1 12h6m6 0h6m-2.66-8L13 7.5M7 16.5l3.66-4.5"/>
            </svg>
            <span className={styles['sidebar-item-text']}>Adjutant</span>
          </Link>

          {/* KB list */}
          {kbs.map(kb => (
            <div key={kb.name} className={styles['sidebar-kb-wrapper']}>
              <button
                className={`${styles['sidebar-item']} ${currentKb === kb.name ? styles.active : ''}`}
                onClick={() => handleKbClick(kb.name)}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
                </svg>
                <span className={styles['sidebar-item-text']}>{kb.name}</span>
              </button>
            </div>
          ))}

          {/* Current folder breadcrumbs + entries */}
          {currentKb && (
            <div className={styles['sidebar-folder-section']}>
              {/* Breadcrumbs */}
              {breadcrumbs.length > 0 && (
                <div className={styles['sidebar-breadcrumbs']}>
                  <button
                    className={styles['sidebar-breadcrumb']}
                    onClick={() => handleBreadcrumbClick(0)}
                  >
                    {currentKb}
                  </button>
                  {breadcrumbs.map((crumb, i) => (
                    <span key={i}>
                      <span className={styles['sidebar-breadcrumb-sep']}>/</span>
                      <button
                        className={styles['sidebar-breadcrumb']}
                        onClick={() => handleBreadcrumbClick(i + 1)}
                      >
                        {crumb}
                      </button>
                    </span>
                  ))}
                </div>
              )}

              {/* Folder entries (recursive tree) */}
              {loading ? (
                <div className={styles['sidebar-loading']}>Loading...</div>
              ) : (
                <div className={styles['sidebar-entries']}>
                  {renderEntryTree(entries, 0)}
                </div>
              )}
            </div>
          )}
        </nav>

        {/* Settings at bottom */}
        <div className={styles['sidebar-footer']}>
          <button className={styles['sidebar-item']} onClick={handleSettingsClick}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
              <path 
                d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" 
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
              />
              <path 
                d="M16.167 12.5a1.375 1.375 0 00.275 1.517l.05.05a1.667 1.667 0 11-2.359 2.358l-.05-.05a1.375 1.375 0 00-1.516-.275 1.375 1.375 0 00-.834 1.258v.142a1.667 1.667 0 11-3.333 0v-.075a1.375 1.375 0 00-.9-1.258 1.375 1.375 0 00-1.517.275l-.05.05a1.667 1.667 0 11-2.358-2.359l.05-.05a1.375 1.375 0 00.275-1.516 1.375 1.375 0 00-1.258-.834H2.5a1.667 1.667 0 010-3.333h.075a1.375 1.375 0 001.258-.9 1.375 1.375 0 00-.275-1.517l-.05-.05a1.667 1.667 0 112.359-2.358l.05.05a1.375 1.375 0 001.516.275h.067a1.375 1.375 0 00.833-1.258V2.5a1.667 1.667 0 013.334 0v.075a1.375 1.375 0 00.833 1.258 1.375 1.375 0 001.517-.275l.05-.05a1.667 1.667 0 112.358 2.359l-.05.05a1.375 1.375 0 00-.275 1.516v.067a1.375 1.375 0 001.258.833h.142a1.667 1.667 0 010 3.334h-.075a1.375 1.375 0 00-1.258.833z" 
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
              />
            </svg>
            <span className={styles['sidebar-item-text']}>Settings</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
