import { useEffect, useCallback, useState, useRef } from 'react';
import type { Settings, Theme } from '../../types';
import styles from './SettingsDialog.module.css';

interface SettingsDialogProps {
  open: boolean;
  settings: Settings;
  onSettingChange: <K extends keyof Settings>(key: K, value: Settings[K]) => void;
  onClose: () => void;
  onKbRootSaved?: () => void;
}

export function SettingsDialog({
  open,
  settings,
  onSettingChange,
  onClose,
  onKbRootSaved,
}: SettingsDialogProps) {
  const [kbRootInput, setKbRootInput] = useState(settings.kbRoot || '');
  const [kbRootError, setKbRootError] = useState<string | null>(null);
  const [kbRootSaving, setKbRootSaving] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const browsingRef = useRef(false);

  // Sync input when settings load
  useEffect(() => {
    setKbRootInput(settings.kbRoot || '');
  }, [settings.kbRoot]);

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

  const handleKbRootSave = useCallback(async () => {
    if (!kbRootInput.trim()) return;
    setKbRootSaving(true);
    setKbRootError(null);
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ kbRoot: kbRootInput.trim() }),
      });
      if (!res.ok) {
        const data = await res.json();
        setKbRootError(data.error || 'Failed to save');
        return;
      }
      onSettingChange('kbRoot', kbRootInput.trim());
      if (onKbRootSaved) onKbRootSaved();
    } catch (err) {
      setKbRootError('Failed to connect to server');
    } finally {
      setKbRootSaving(false);
    }
  }, [kbRootInput, onSettingChange, onKbRootSaved]);

  const handleBrowse = useCallback(async () => {
    if (browsingRef.current) return;
    browsingRef.current = true;
    setBrowsing(true);
    setKbRootError(null);
    try {
      const res = await fetch('/api/config/browse', { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        setKbRootError(data.error || 'Browse not supported');
        return;
      }
      const data = await res.json();
      if (!data.cancelled && data.path) {
        setKbRootInput(data.path);
      }
    } catch {
      setKbRootError('Failed to open directory picker');
    } finally {
      setBrowsing(false);
      browsingRef.current = false;
    }
  }, []);

  if (!open) return null;

  return (
    <div className={styles['dialog-overlay']} onClick={onClose}>
      <div className={styles['settings-dialog']} onClick={e => e.stopPropagation()}>
        <div className={styles['settings-header']}>
          <h2 className={styles['settings-title']}>Settings</h2>
          <button className={styles['settings-close']} onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 4L4 12M4 4l8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>
        
        <div className={styles['settings-content']}>
          {/* KB Root Directory */}
          <div className={styles['settings-section']}>
            <h3 className={styles['settings-section-title']}>Knowledge Bases</h3>
            
            <div className={styles['settings-field']}>
              <span className={styles['settings-select-label']}>
                <span className={styles['settings-select-title']}>KB Root Directory</span>
                <span className={styles['settings-select-description']}>
                  Parent directory containing your knowledge bases (folders with kb.yaml)
                </span>
              </span>
              <div className={styles['settings-kb-root']}>
                <input
                  type="text"
                  value={kbRootInput}
                  onChange={e => { setKbRootInput(e.target.value); setKbRootError(null); }}
                  placeholder="/path/to/knowledge-bases"
                  className={styles['settings-text-input']}
                  onKeyDown={e => { if (e.key === 'Enter') handleKbRootSave(); }}
                />
                <button
                  className={styles['settings-browse-btn']}
                  onClick={handleBrowse}
                  disabled={browsing}
                  title="Browse with Finder"
                >
                  {browsing ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={styles['settings-browse-spinner']}>
                      <path d="M21 12a9 9 0 11-6.219-8.56"/>
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                    </svg>
                  )}
                </button>
                <button
                  className={styles['settings-kb-root-save']}
                  onClick={handleKbRootSave}
                  disabled={kbRootSaving || !kbRootInput.trim()}
                >
                  {kbRootSaving ? 'Saving...' : 'Save'}
                </button>
              </div>
              {kbRootError && (
                <span className={styles['settings-error']}>{kbRootError}</span>
              )}
              {settings.kbRoot && (
                <button
                  className={styles['settings-reveal-btn']}
                  onClick={() => {
                    fetch('/api/config/reveal', {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ path: settings.kbRoot }),
                    }).catch(() => {});
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                    <polyline points="15 3 21 3 21 9"/>
                    <line x1="10" y1="14" x2="21" y2="3"/>
                  </svg>
                  Reveal in Finder
                </button>
              )}
            </div>
          </div>

          {/* Appearance */}
          <div className={styles['settings-section']}>
            <h3 className={styles['settings-section-title']}>Appearance</h3>
            
            <div className={styles['settings-select']}>
              <span className={styles['settings-select-label']}>
                <span className={styles['settings-select-title']}>Theme</span>
                <span className={styles['settings-select-description']}>
                  Choose the visual style of the application
                </span>
              </span>
              <select
                value={settings.theme}
                onChange={e => onSettingChange('theme', e.target.value as Theme)}
                className={styles['settings-select-input']}
              >
                <option value="default">Default</option>
                <option value="bauhaus">Bauhaus</option>
              </select>
            </div>
          </div>
          
          {/* Canvas */}
          <div className={styles['settings-section']}>
            <h3 className={styles['settings-section-title']}>Canvas</h3>
            
            <label className={styles['settings-toggle']}>
              <span className={styles['settings-toggle-label']}>
                <span className={styles['settings-toggle-title']}>Snap to object</span>
                <span className={styles['settings-toggle-description']}>
                  Automatically align items to nearby objects while dragging
                </span>
              </span>
              <input
                type="checkbox"
                checked={settings.snapToObject}
                onChange={e => onSettingChange('snapToObject', e.target.checked)}
              />
              <span className={styles['settings-toggle-switch']} />
            </label>
            
            <label className={styles['settings-toggle']}>
              <span className={styles['settings-toggle-label']}>
                <span className={styles['settings-toggle-title']}>Show snap lines</span>
                <span className={styles['settings-toggle-description']}>
                  Display alignment guides when snapping to objects
                </span>
              </span>
              <input
                type="checkbox"
                checked={settings.showSnapLines}
                onChange={e => onSettingChange('showSnapLines', e.target.checked)}
              />
              <span className={styles['settings-toggle-switch']} />
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsDialog;
