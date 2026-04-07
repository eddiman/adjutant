/**
 * Session list with KB-grouped tree view.
 *
 * Shows all KBs from adjutant + custom folders from localStorage.
 * Sessions are grouped under the KB/folder whose path matches session.cwd.
 * Each folder has a [+ New Session] button for quick-start.
 */

import { useEffect, useState, useCallback } from 'react';
import type { SessionInfo } from '../../hooks/useCodeSession';
import type { KbMeta } from '../../types';

// CLI session from ~/.claude/projects/ — read-only, resumable via --resume
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
  try {
    return JSON.parse(localStorage.getItem(FOLDERS_KEY) || '[]');
  } catch { return []; }
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

// === Session row (compact) ===

function SessionRow({ session, onResume, onDelete }: {
  session: SessionInfo;
  onResume: (id: string) => void;
  onDelete?: (id: string) => void;
}) {
  const name = session.name || 'New session';
  return (
    <button
      onClick={() => onResume(session.id)}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        width: '100%', padding: '0.375rem 0 0.375rem 1.25rem',
        background: 'none', border: 'none', borderBottom: '1px solid rgba(42,43,61,0.3)',
        cursor: 'pointer', color: 'inherit', textAlign: 'left', fontFamily: 'inherit',
        transition: 'background 0.1s', gap: '0.5rem',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(124,92,191,0.06)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'none')}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: '0.75rem', color: 'var(--cs-text-secondary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {name}
        </div>
        <div style={{ fontSize: '0.625rem', color: 'var(--cs-text-muted)', display: 'flex', gap: '0.5rem' }}>
          <span>{relativeTime(session.lastActiveAt)}</span>
          <span>{session.messages.length} msg{session.messages.length !== 1 ? 's' : ''}</span>
          {session.totalCostUsd != null && session.totalCostUsd > 0 && (
            <span>${session.totalCostUsd.toFixed(4)}</span>
          )}
        </div>
      </div>
      {onDelete && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
          style={{
            background: 'none', border: 'none', color: 'var(--cs-text-muted)',
            cursor: 'pointer', padding: '0.125rem 0.25rem', fontSize: '0.625rem',
            flexShrink: 0, transition: 'color 0.1s',
          }}
          onMouseEnter={e => (e.currentTarget.style.color = '#f56c6c')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--cs-text-muted)')}
        >
          x
        </button>
      )}
    </button>
  );
}

// === CLI session row (from ~/.claude/projects/) ===

function CliSessionRow({ session, onResume }: {
  session: CliSessionSummary;
  onResume: (id: string) => void;
}) {
  return (
    <button
      onClick={() => onResume(session.id)}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        width: '100%', padding: '0.375rem 0 0.375rem 1.25rem',
        background: 'none', border: 'none', borderBottom: '1px solid rgba(42,43,61,0.3)',
        cursor: 'pointer', color: 'inherit', textAlign: 'left', fontFamily: 'inherit',
        transition: 'background 0.1s', gap: '0.5rem',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(124,92,191,0.06)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'none')}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: '0.75rem', color: 'var(--cs-text-secondary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {session.name}
        </div>
        <div style={{ fontSize: '0.625rem', color: 'var(--cs-text-muted)', display: 'flex', gap: '0.5rem' }}>
          <span>{relativeTime(session.timestamp)}</span>
          <span>{session.messageCount} msg{session.messageCount !== 1 ? 's' : ''}</span>
          {session.model && <span style={{ opacity: 0.7 }}>{session.model}</span>}
        </div>
      </div>
    </button>
  );
}

// === Folder group (KB or custom folder) ===

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
  return (
    <div style={{ borderBottom: '1px solid var(--cs-border)' }}>
      {/* Folder header */}
      <div
        style={{
          display: 'flex', alignItems: 'center', padding: '0.5rem 0.75rem',
          cursor: 'pointer', transition: 'background 0.1s', gap: '0.5rem',
        }}
        onClick={onToggle}
        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(124,92,191,0.04)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'none')}
      >
        <span style={{ fontSize: '0.75rem', opacity: 0.5, flexShrink: 0, transition: 'transform 0.15s', transform: expanded ? 'rotate(90deg)' : 'none' }}>
          ▶
        </span>
        <span style={{ fontSize: '0.8125rem', flexShrink: 0 }}>{icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '0.8125rem', color: 'var(--cs-text)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {label}
          </div>
          <div style={{ fontSize: '0.625rem', color: 'var(--cs-text-muted)', fontFamily: "'SF Mono', monospace", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {path}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.25rem', flexShrink: 0 }}>
          {(sessions.length + cliSessions.length) > 0 && (
            <span style={{ fontSize: '0.625rem', color: 'var(--cs-text-muted)', padding: '0 0.25rem' }}>
              {sessions.length + cliSessions.length}
            </span>
          )}
          <button
            onClick={e => { e.stopPropagation(); onNewSession(path); }}
            style={{
              background: 'rgba(124,92,191,0.1)', border: 'none', color: 'var(--cs-accent)',
              cursor: 'pointer', padding: '0.125rem 0.375rem', fontSize: '0.625rem',
              borderRadius: '0.1875rem', fontWeight: 500,
            }}
          >
            + New
          </button>
          {onRemoveFolder && (
            <button
              onClick={e => { e.stopPropagation(); onRemoveFolder(); }}
              style={{
                background: 'none', border: 'none', color: 'var(--cs-text-muted)',
                cursor: 'pointer', padding: '0.125rem 0.25rem', fontSize: '0.625rem',
                transition: 'color 0.1s',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = '#f56c6c')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--cs-text-muted)')}
              title="Remove folder"
            >
              x
            </button>
          )}
        </div>
      </div>

      {/* Sessions under this folder */}
      {expanded && (
        <div>
          {sessions.length === 0 && cliSessions.length === 0 ? (
            <div style={{ padding: '0.25rem 0 0.375rem 2.25rem', fontSize: '0.6875rem', color: 'var(--cs-text-muted)', fontStyle: 'italic' }}>
              No sessions
            </div>
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
      )}
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

  // Adjutant root first (if available and not already a KB path)
  if (adjutantDir && !kbs.some(kb => kb.path === adjutantDir)) {
    const matching = sessions.filter(s => matchPath(s.cwd, adjutantDir));
    matching.forEach(s => claimed.add(s.id));
    const matchingCli = cliSessions.filter(s => matchPath(s.cwd, adjutantDir));
    matchingCli.forEach(s => claimedCli.add(s.id));
    groups.push({ icon: '🏠', label: 'Adjutant', path: adjutantDir, isKb: true, sessions: matching, cliSessions: matchingCli });
  }

  // KBs
  for (const kb of kbs) {
    const matching = sessions.filter(s => !claimed.has(s.id) && matchPath(s.cwd, kb.path));
    matching.forEach(s => claimed.add(s.id));
    const matchingCli = cliSessions.filter(s => !claimedCli.has(s.id) && matchPath(s.cwd, kb.path));
    matchingCli.forEach(s => claimedCli.add(s.id));
    groups.push({ icon: '📚', label: kb.name, path: kb.path, isKb: true, sessions: matching, cliSessions: matchingCli });
  }

  // Custom folders
  for (const folder of customFolders) {
    if (kbs.some(kb => kb.path === folder)) continue;
    if (adjutantDir && folder === adjutantDir) continue;
    const matching = sessions.filter(s => !claimed.has(s.id) && matchPath(s.cwd, folder));
    matching.forEach(s => claimed.add(s.id));
    const matchingCli = cliSessions.filter(s => !claimedCli.has(s.id) && matchPath(s.cwd, folder));
    matchingCli.forEach(s => claimedCli.add(s.id));
    groups.push({ icon: '📁', label: pathLabel(folder), path: folder, isKb: false, sessions: matching, cliSessions: matchingCli });
  }

  const orphans = sessions.filter(s => !claimed.has(s.id));
  return { groups, orphans };
}

// === Modal session list ===

interface SessionListProps {
  open: boolean;
  onResume: (sessionId: string) => void;
  onResumeCliSession: (cliSessionId: string, cwd: string) => void;
  onNewSession: (cwd: string) => void;
  onAddFolder: () => void;
  onClose: () => void;
}

export function SessionList({ open, onResume, onResumeCliSession, onNewSession, onAddFolder, onClose }: SessionListProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [cliSessions, setCliSessions] = useState<CliSessionSummary[]>([]);
  const [kbs, setKbs] = useState<KbMeta[]>([]);
  const [adjutantDir, setAdjutantDir] = useState<string | null>(null);
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!open) return;
    setLoading(true);
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
      })
      .catch(() => { setSessions([]); setCliSessions([]); setKbs([]); })
      .finally(() => setLoading(false));
  }, [open]);

  // Auto-expand folders that have sessions
  useEffect(() => {
    if (!loading && (sessions.length > 0 || cliSessions.length > 0)) {
      const { groups } = groupSessions(kbs, customFolders, sessions, adjutantDir, cliSessions);
      setExpanded(new Set(groups.filter(g => g.sessions.length > 0 || g.cliSessions.length > 0).map(g => g.path)));
    }
  }, [loading, sessions, cliSessions, kbs, customFolders, adjutantDir]);

  const handleDelete = useCallback(async (id: string) => {
    await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    setSessions(prev => prev.filter(s => s.id !== id));
  }, []);

  const handleRemoveFolder = useCallback((folder: string) => {
    const next = customFolders.filter(f => f !== folder);
    setCustomFolders(next);
    saveCustomFolders(next);
  }, [customFolders]);

  const toggleExpand = useCallback((path: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler, { capture: true });
    return () => window.removeEventListener('keydown', handler, { capture: true });
  }, [open, onClose]);

  if (!open) return null;

  const { groups, orphans } = groupSessions(kbs, customFolders, sessions, adjutantDir, cliSessions);

  const handleResumeCliSession = (sessionId: string, cwd: string) => {
    onResumeCliSession(sessionId, cwd);
    onClose();
  };

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
          borderRadius: '0.5rem', width: '34rem', maxWidth: '95vw', maxHeight: '32rem',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{
          padding: '0.75rem 1rem', borderBottom: '1px solid var(--cs-border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <h3 style={{ margin: 0, fontSize: '0.875rem', color: 'var(--cs-text)' }}>Sessions</h3>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              onClick={onAddFolder}
              style={{
                background: 'rgba(124,92,191,0.1)', border: 'none', color: 'var(--cs-accent)',
                cursor: 'pointer', padding: '0.25rem 0.5rem', fontSize: '0.75rem',
                borderRadius: '0.25rem', fontWeight: 500,
              }}
            >
              + Add Folder
            </button>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', color: 'var(--cs-text-muted)', cursor: 'pointer', fontSize: '1rem' }}
            >
              x
            </button>
          </div>
        </div>

        {/* Tree content */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {loading ? (
            <p style={{ padding: '1rem', textAlign: 'center', color: 'var(--cs-text-muted)', fontSize: '0.8125rem' }}>Loading...</p>
          ) : groups.length === 0 && orphans.length === 0 ? (
            <p style={{ padding: '1rem', textAlign: 'center', color: 'var(--cs-text-muted)', fontSize: '0.8125rem' }}>
              No KBs or folders configured. Add a folder to get started.
            </p>
          ) : (
            <>
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
                  onNewSession={(cwd) => { onNewSession(cwd); onClose(); }}
                  onResume={(id) => { onResume(id); onClose(); }}
                  onResumeCliSession={handleResumeCliSession}
                  onDelete={handleDelete}
                  onRemoveFolder={g.isKb ? undefined : () => handleRemoveFolder(g.path)}
                />
              ))}
              {/* Orphan sessions (CWD doesn't match any KB/folder) */}
              {orphans.length > 0 && (
                <FolderGroup
                  icon="📄"
                  label="Other"
                  path=""
                  sessions={orphans}
                  cliSessions={[]}
                  expanded={expanded.has('__orphans__')}
                  onToggle={() => toggleExpand('__orphans__')}
                  onNewSession={() => {}}
                  onResume={(id) => { onResume(id); onClose(); }}
                  onDelete={handleDelete}
                />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// === Inline start screen (KB-grouped) ===

interface StartScreenSessionsProps {
  onResume: (sessionId: string) => void;
  onResumeCliSession: (cliSessionId: string, cwd: string) => void;
  onNewSession: (cwd: string) => void;
  onShowAll: () => void;
  onAddFolder: () => void;
}

export function StartScreenSessions({ onResume, onResumeCliSession, onNewSession, onShowAll, onAddFolder }: StartScreenSessionsProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [cliSessions, setCliSessions] = useState<CliSessionSummary[]>([]);
  const [kbs, setKbs] = useState<KbMeta[]>([]);
  const [adjutantDir, setAdjutantDir] = useState<string | null>(null);
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setCustomFolders(loadCustomFolders());
    Promise.all([
      fetch('/api/sessions').then(r => r.json()).then(d => ({ sessions: d.sessions || [], cliSessions: d.cliSessions || [] })),
      fetch('/api/kbs').then(r => r.json()).then(d => d.kbs || []),
      fetch('/api/adjutant/status').then(r => r.json()).then(d => d.adjutantDir || null).catch(() => null),
    ])
      .then(([sessData, kbList, adjDir]) => { setSessions(sessData.sessions); setCliSessions(sessData.cliSessions); setKbs(kbList); setAdjutantDir(adjDir); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Auto-expand all on load
  useEffect(() => {
    if (!loading) {
      const { groups } = groupSessions(kbs, customFolders, sessions, adjutantDir, cliSessions);
      setExpanded(new Set(groups.map(g => g.path)));
    }
  }, [loading, kbs, customFolders, sessions, cliSessions, adjutantDir]);

  const toggleExpand = useCallback((path: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }, []);

  const handleRemoveFolder = useCallback((folder: string) => {
    const next = customFolders.filter(f => f !== folder);
    setCustomFolders(next);
    saveCustomFolders(next);
  }, [customFolders]);

  if (loading) return null;

  const { groups, orphans } = groupSessions(kbs, customFolders, sessions, adjutantDir, cliSessions);
  const hasContent = groups.length > 0 || orphans.length > 0;

  if (!hasContent) return null;

  return (
    <div style={{ width: '100%', maxWidth: '34rem', marginTop: '0.5rem' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '0.25rem', padding: '0 0.25rem',
      }}>
        <h3 style={{
          margin: 0, fontSize: '0.75rem', fontWeight: 600,
          color: 'var(--cs-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          Workspaces
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={onAddFolder}
            style={{
              background: 'none', border: 'none', color: 'var(--cs-accent)',
              cursor: 'pointer', fontSize: '0.75rem', padding: 0,
            }}
          >
            + Add folder
          </button>
          <button
            onClick={onShowAll}
            style={{
              background: 'none', border: 'none', color: 'var(--cs-accent)',
              cursor: 'pointer', fontSize: '0.75rem', padding: 0,
            }}
          >
            View all
          </button>
        </div>
      </div>
      <div style={{
        border: '1px solid var(--cs-border)', borderRadius: '0.375rem',
        overflow: 'hidden',
      }}>
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
            onRemoveFolder={g.isKb ? undefined : () => handleRemoveFolder(g.path)}
          />
        ))}
        {orphans.length > 0 && (
          <FolderGroup
            icon="📄"
            label="Other"
            path=""
            sessions={orphans}
            cliSessions={[]}
            expanded={expanded.has('__orphans__')}
            onToggle={() => toggleExpand('__orphans__')}
            onNewSession={() => {}}
            onResume={onResume}
          />
        )}
      </div>
    </div>
  );
}

// === Helper: add a folder to localStorage ===

export function addCustomFolder(path: string): void {
  const folders = loadCustomFolders();
  if (!folders.includes(path)) {
    folders.push(path);
    saveCustomFolders(folders);
  }
}
