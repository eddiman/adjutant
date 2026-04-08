/**
 * Session list components.
 *
 * ChatSessionList — inline page for /chat route (flat accordions)
 * SessionList     — modal overlay (kept for backward compat)
 */

import { useEffect, useState, useCallback } from 'react';
import type { SessionInfo } from '../../hooks/useCodeSession';
import type { KbMeta } from '../../types';
import styles from './SessionList.module.css';

export interface CliSessionSummary {
  id: string;
  name: string;
  cwd: string;
  model: string;
  timestamp: string;
  messageCount: number;
  source: 'cli';
}

const FOLDERS_KEY = 'adjutant-code-session-folders';

function loadCustomFolders(): string[] {
  try { return JSON.parse(localStorage.getItem(FOLDERS_KEY) || '[]'); } catch { return []; }
}

function saveCustomFolders(folders: string[]): void {
  try { localStorage.setItem(FOLDERS_KEY, JSON.stringify(folders)); } catch { /* ignore */ }
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function pathLabel(p: string): string {
  const parts = p.split('/').filter(Boolean);
  return parts.length > 1 ? parts.slice(-2).join('/') : parts[parts.length - 1] || p;
}

// === Inline SVG icons (matching Sidebar) ===

function IconChevron({ expanded }: { expanded?: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.25s ease' }}
    >
      <polyline points="9 18 15 12 9 6"/>
    </svg>
  );
}

function IconHome() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
      <polyline points="9 22 9 12 15 12 15 22"/>
    </svg>
  );
}

function IconBook() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
    </svg>
  );
}

function IconFolder() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
    </svg>
  );
}

function IconDocument() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
    </svg>
  );
}

function IconClose() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="6" x2="6" y2="18"/>
      <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  );
}

function IconAdd() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="5" x2="12" y2="19"/>
      <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );
}

const ICON_MAP: Record<string, () => JSX.Element> = {
  home: IconHome,
  book: IconBook,
  folder: IconFolder,
  document: IconDocument,
};

// === Session row ===

function SessionRow({ session, onResume, onDelete }: {
  session: SessionInfo;
  onResume: (id: string) => void;
  onDelete?: (id: string) => void;
}) {
  return (
    <div className={styles.sessionRow} onClick={() => onResume(session.id)} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onResume(session.id); }}>
      <div className={styles.sessionInfo}>
        <div className={styles.sessionName}>{session.name || 'New session'}</div>
        <div className={styles.sessionMeta}>
          <span>{relativeTime(session.lastActiveAt)}</span>
          <span>{session.messages.length} msg{session.messages.length !== 1 ? 's' : ''}</span>
          {session.totalCostUsd != null && session.totalCostUsd > 0 && (
            <span>${session.totalCostUsd.toFixed(4)}</span>
          )}
        </div>
      </div>
      {onDelete && (
        <button
          className={styles.sessionDeleteBtn}
          onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
        >
          <IconClose />
        </button>
      )}
    </div>
  );
}

function CliSessionRow({ session, onResume }: {
  session: CliSessionSummary;
  onResume: (id: string) => void;
}) {
  return (
    <div className={styles.sessionRow} onClick={() => onResume(session.id)} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onResume(session.id); }}>
      <div className={styles.sessionInfo}>
        <div className={styles.sessionName}>{session.name}</div>
        <div className={styles.sessionMeta}>
          <span>{relativeTime(session.timestamp)}</span>
          <span>{session.messageCount} msg{session.messageCount !== 1 ? 's' : ''}</span>
          {session.model && <span>{session.model}</span>}
        </div>
      </div>
    </div>
  );
}

// === Folder group ===

function FolderGroup({ icon, label, path, sessions, cliSessions, expanded, onToggle, onNewSession, onResume, onResumeCliSession, onDelete, onRemoveFolder }: {
  icon: string;
  label: string;
  path: string;
  sessions: SessionInfo[];
  cliSessions: CliSessionSummary[];
  expanded: boolean;
  onToggle: () => void;
  onNewSession: (cwd: string) => void;
  onResume: (id: string) => void;
  onResumeCliSession?: (id: string, cwd: string) => void;
  onDelete?: (id: string) => void;
  onRemoveFolder?: () => void;
}) {
  const count = sessions.length + cliSessions.length;
  const IconComponent = ICON_MAP[icon] || IconFolder;

  return (
    <div className={styles.folderCard}>
      <div className={styles.folderHeader} onClick={onToggle}>
        <span className={styles.folderChevron}>
          <IconChevron expanded={expanded} />
        </span>
        <span className={styles.folderIcon}>
          <IconComponent />
        </span>
        <div className={styles.folderInfo}>
          <div className={styles.folderLabel}>{label}</div>
          <div className={styles.folderPath}>{path}</div>
        </div>
        <div className={styles.folderActions}>
          {count > 0 && <span className={styles.folderCount}>{count}</span>}
          <button
            className={styles.folderNewBtn}
            onClick={e => { e.stopPropagation(); onNewSession(path); }}
          >
            <IconAdd />
            New
          </button>
          {onRemoveFolder && (
            <button
              className={styles.folderRemoveBtn}
              onClick={e => { e.stopPropagation(); onRemoveFolder(); }}
              title="Remove folder"
            >
              <IconClose />
            </button>
          )}
        </div>
      </div>

      <div className={`${styles.sessionListWrapper} ${expanded ? styles.sessionListWrapperExpanded : ''}`}>
        <div className={styles.sessionList}>
          <div className={styles.sessionListContent}>
            {sessions.length === 0 && cliSessions.length === 0 ? (
              <div className={styles.emptyFolder}>No sessions</div>
            ) : (
              <>
                {sessions.map(s => (
                  <SessionRow key={s.id} session={s} onResume={onResume} onDelete={onDelete} />
                ))}
                {cliSessions.map(s => (
                  <CliSessionRow key={`cli-${s.id}`} session={s} onResume={() => onResumeCliSession?.(s.id, s.cwd)} />
                ))}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// === Grouping logic ===

interface FolderEntry {
  icon: string;
  label: string;
  path: string;
  isKb: boolean;
  sessions: SessionInfo[];
  cliSessions: CliSessionSummary[];
}

function matchPath(cwd: string, folderPath: string): boolean {
  return cwd === folderPath || cwd.startsWith(folderPath + '/');
}

function groupSessions(
  kbs: KbMeta[],
  customFolders: string[],
  sessions: SessionInfo[],
  adjutantDir: string | null,
  cliSessions: CliSessionSummary[] = [],
): { groups: FolderEntry[]; orphans: SessionInfo[] } {
  const groups: FolderEntry[] = [];
  const claimed = new Set<string>();
  const claimedCli = new Set<string>();

  if (adjutantDir && !kbs.some(kb => kb.path === adjutantDir)) {
    const matching = sessions.filter(s => matchPath(s.cwd, adjutantDir));
    matching.forEach(s => claimed.add(s.id));
    const matchingCli = cliSessions.filter(s => matchPath(s.cwd, adjutantDir));
    matchingCli.forEach(s => claimedCli.add(s.id));
    groups.push({ icon: 'home', label: 'Adjutant', path: adjutantDir, isKb: true, sessions: matching, cliSessions: matchingCli });
  }

  for (const kb of kbs) {
    const matching = sessions.filter(s => !claimed.has(s.id) && matchPath(s.cwd, kb.path));
    matching.forEach(s => claimed.add(s.id));
    const matchingCli = cliSessions.filter(s => !claimedCli.has(s.id) && matchPath(s.cwd, kb.path));
    matchingCli.forEach(s => claimedCli.add(s.id));
    groups.push({ icon: 'book', label: kb.name, path: kb.path, isKb: true, sessions: matching, cliSessions: matchingCli });
  }

  for (const folder of customFolders) {
    if (kbs.some(kb => kb.path === folder)) continue;
    if (adjutantDir && folder === adjutantDir) continue;
    const matching = sessions.filter(s => !claimed.has(s.id) && matchPath(s.cwd, folder));
    matching.forEach(s => claimed.add(s.id));
    const matchingCli = cliSessions.filter(s => !claimedCli.has(s.id) && matchPath(s.cwd, folder));
    matchingCli.forEach(s => claimedCli.add(s.id));
    groups.push({ icon: 'folder', label: pathLabel(folder), path: folder, isKb: false, sessions: matching, cliSessions: matchingCli });
  }

  const orphans = sessions.filter(s => !claimed.has(s.id));
  return { groups, orphans };
}

// ============================================================
// ChatSessionList — inline page component for /chat route
// ============================================================

interface ChatSessionListProps {
  onResume: (sessionId: string) => void;
  onResumeCliSession: (cliSessionId: string, cwd: string) => void;
  onNewSession: (cwd: string) => void;
}

export function ChatSessionList({ onResume, onResumeCliSession, onNewSession }: ChatSessionListProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [cliSessions, setCliSessions] = useState<CliSessionSummary[]>([]);
  const [kbs, setKbs] = useState<KbMeta[]>([]);
  const [adjutantDir, setAdjutantDir] = useState<string | null>(null);
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set(['__all__']));

  useEffect(() => {
    setCustomFolders(loadCustomFolders());
    Promise.all([
      fetch('/api/sessions').then(r => r.json()).then(d => ({ sessions: d.sessions || [], cliSessions: d.cliSessions || [] })),
      fetch('/api/kbs').then(r => r.json()).then(d => d.kbs || []),
      fetch('/api/adjutant/status').then(r => r.json()).then(d => d.adjutantDir || null).catch(() => null),
    ])
      .then(([sessData, kbList, adjDir]) => {
        setSessions(sessData.sessions);
        setCliSessions(sessData.cliSessions);
        setKbs(kbList);
        setAdjutantDir(adjDir);
        // Auto-expand first group
        const { groups } = groupSessions(kbList, loadCustomFolders(), sessData.sessions, adjDir, sessData.cliSessions);
        if (groups.length > 0) {
          setExpanded(new Set([groups[0].path]));
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const toggleExpand = useCallback((path: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    setSessions(prev => prev.filter(s => s.id !== id));
  }, []);

  const handleRemoveFolder = useCallback((folder: string) => {
    const next = customFolders.filter(f => f !== folder);
    setCustomFolders(next);
    saveCustomFolders(next);
  }, [customFolders]);

  if (loading) {
    return <p className={styles.loading}>Loading sessions...</p>;
  }

  const { groups, orphans } = groupSessions(kbs, customFolders, sessions, adjutantDir, cliSessions);

  if (groups.length === 0 && orphans.length === 0) {
    return <p className={styles.empty}>No sessions yet. Start a new chat to begin.</p>;
  }

  return (
    <div className={styles.list}>
      {groups.map(g => (
        <FolderGroup
          key={g.path}
          icon={g.icon}
          label={g.label}
          path={g.path}
          sessions={g.sessions}
          cliSessions={g.cliSessions}
          expanded={expanded.has(g.path)}
          onToggle={() => toggleExpand(g.path)}
          onNewSession={onNewSession}
          onResume={onResume}
          onResumeCliSession={onResumeCliSession}
          onDelete={handleDelete}
          onRemoveFolder={g.isKb ? undefined : () => handleRemoveFolder(g.path)}
        />
      ))}
      {orphans.length > 0 && (
        <FolderGroup
          icon="document"
          label="Other"
          path=""
          sessions={orphans}
          cliSessions={[]}
          expanded={expanded.has('__orphans__')}
          onToggle={() => toggleExpand('__orphans__')}
          onNewSession={() => {}}
          onResume={onResume}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}

// ============================================================
// Helper: add a folder to localStorage
// ============================================================

export function addCustomFolder(path: string): void {
  const folders = loadCustomFolders();
  if (!folders.includes(path)) {
    folders.push(path);
    saveCustomFolders(folders);
  }
}
