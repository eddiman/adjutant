import { useEffect, useState, useCallback } from 'react';
import type { SessionInfo } from '../../hooks/useCodeSession';

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

function firstUserMessage(session: SessionInfo): string {
  const msg = session.messages.find(m => m.role === 'user');
  return msg ? msg.content.slice(0, 100) : 'No messages';
}

// === Shared session row ===

interface SessionRowProps {
  session: SessionInfo;
  onResume: (id: string) => void;
  onDelete?: (id: string, e: React.MouseEvent) => void;
  compact?: boolean;
}

function SessionRow({ session, onResume, onDelete, compact }: SessionRowProps) {
  const msgCount = session.messages.length;
  const name = session.name || firstUserMessage(session);
  const cwdShort = session.cwd.split('/').slice(-2).join('/');

  return (
    <button
      onClick={() => onResume(session.id)}
      style={{
        display: 'flex', flexDirection: 'column', gap: compact ? '0.125rem' : '0.25rem',
        width: '100%', padding: compact ? '0.5rem 0' : '0.625rem 1rem',
        background: 'none', border: 'none',
        borderBottom: '1px solid var(--cs-border)', cursor: 'pointer',
        color: 'inherit', textAlign: 'left', fontFamily: 'inherit',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => (e.currentTarget.style.background = 'rgba(124,92,191,0.06)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'none')}
    >
      {/* Top row: time + meta */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--cs-text)', fontWeight: 500 }}>
            {relativeTime(session.lastActiveAt)}
          </span>
          <span style={{
            fontSize: '0.6875rem', color: 'var(--cs-text-muted)',
            background: 'rgba(124,92,191,0.1)', padding: '0.0625rem 0.375rem',
            borderRadius: '0.1875rem',
          }}>
            {session.backend}
          </span>
          <span style={{ fontSize: '0.6875rem', color: 'var(--cs-text-muted)' }}>
            {msgCount} msg{msgCount !== 1 ? 's' : ''}
          </span>
        </div>
        {onDelete && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(session.id, e); }}
            style={{
              background: 'none', border: 'none', color: 'var(--cs-text-muted)',
              cursor: 'pointer', padding: '0.125rem 0.375rem', fontSize: '0.6875rem',
              borderRadius: '0.1875rem', transition: 'color 0.1s',
            }}
            onMouseEnter={e => (e.currentTarget.style.color = '#f56c6c')}
            onMouseLeave={e => (e.currentTarget.style.color = 'var(--cs-text-muted)')}
          >
            Delete
          </button>
        )}
      </div>

      {/* Session name */}
      <div style={{
        fontSize: '0.75rem', color: 'var(--cs-text-secondary)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        lineHeight: '1.4',
      }}>
        {name}
      </div>

      {/* CWD + model */}
      <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.6875rem', color: 'var(--cs-text-muted)' }}>
        <span style={{ fontFamily: "'SF Mono', 'Fira Code', monospace" }}>{cwdShort}</span>
        <span>{session.model}</span>
        {session.totalCostUsd != null && session.totalCostUsd > 0 && (
          <span>${session.totalCostUsd.toFixed(4)}</span>
        )}
      </div>
    </button>
  );
}

// === Modal session list ===

interface SessionListProps {
  open: boolean;
  onResume: (sessionId: string) => void;
  onClose: () => void;
}

export function SessionList({ open, onResume, onClose }: SessionListProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetch('/api/sessions')
      .then(r => r.json())
      .then(data => setSessions(data.sessions || []))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [open]);

  const handleDelete = useCallback(async (id: string, _e: React.MouseEvent) => {
    await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
    setSessions(prev => prev.filter(s => s.id !== id));
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler, { capture: true });
    return () => window.removeEventListener('keydown', handler, { capture: true });
  }, [open, onClose]);

  if (!open) return null;

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
          <h3 style={{ margin: 0, fontSize: '0.875rem', color: 'var(--cs-text)' }}>All Sessions</h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--cs-text-muted)', cursor: 'pointer', fontSize: '1rem' }}
          >
            x
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 1rem' }}>
          {loading ? (
            <p style={{ padding: '1rem 0', textAlign: 'center', color: 'var(--cs-text-muted)', fontSize: '0.8125rem' }}>Loading...</p>
          ) : sessions.length === 0 ? (
            <p style={{ padding: '1rem 0', textAlign: 'center', color: 'var(--cs-text-muted)', fontSize: '0.8125rem' }}>No sessions yet</p>
          ) : (
            sessions.map(s => (
              <SessionRow
                key={s.id}
                session={s}
                onResume={(id) => { onResume(id); onClose(); }}
                onDelete={handleDelete}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// === Inline recent sessions (for start screen) ===

interface RecentSessionsProps {
  onResume: (sessionId: string) => void;
  onShowAll: () => void;
}

export function RecentSessions({ onResume, onShowAll }: RecentSessionsProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/sessions')
      .then(r => r.json())
      .then(data => setSessions((data.sessions || []).slice(0, 5)))
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;
  if (sessions.length === 0) return null;

  return (
    <div style={{ width: '100%', maxWidth: '32rem', marginTop: '0.5rem' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '0.25rem', padding: '0 0.25rem',
      }}>
        <h3 style={{
          margin: 0, fontSize: '0.75rem', fontWeight: 600,
          color: 'var(--cs-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          Recent Sessions
        </h3>
        {sessions.length >= 5 && (
          <button
            onClick={onShowAll}
            style={{
              background: 'none', border: 'none', color: 'var(--cs-accent)',
              cursor: 'pointer', fontSize: '0.75rem', padding: 0,
            }}
          >
            View all
          </button>
        )}
      </div>
      <div style={{
        border: '1px solid var(--cs-border)', borderRadius: '0.375rem',
        overflow: 'hidden', padding: '0 0.75rem',
      }}>
        {sessions.map(s => (
          <SessionRow key={s.id} session={s} onResume={onResume} compact />
        ))}
      </div>
    </div>
  );
}
