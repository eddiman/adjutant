import type { SessionInfo, CliBackendInfo } from '../../hooks/useCodeSession';
import styles from './CodeSession.module.css';

interface SessionHeaderProps {
  session: SessionInfo;
  backendInfo: CliBackendInfo | null;
  isResumed?: boolean;
  onNewSession: () => void;
  onShowSessions: () => void;
}

export function SessionHeader({ session, backendInfo, isResumed, onNewSession, onShowSessions }: SessionHeaderProps) {
  return (
    <div className={styles.header}>
      <div className={styles.headerLeft}>
        <span className={styles.headerTitle} title={session.name}>
          {session.name}
        </span>
        <span className={styles.headerBadge}>
          {session.model}
        </span>
        {session.totalCostUsd != null && backendInfo?.name === 'claude-cli' && (
          <span style={{ color: 'var(--cs-text-muted)', fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
            ${session.totalCostUsd.toFixed(4)}
          </span>
        )}
      </div>
      <div className={styles.headerActions}>
        <button className={styles.headerBtn} onClick={onShowSessions}>
          Sessions
        </button>
        <button
          className={`${styles.startBtn} ${styles.headerBtn}`}
          onClick={onNewSession}
          style={{ background: 'var(--cs-accent)', color: '#fff', border: 'none' }}
        >
          + New
        </button>
      </div>
    </div>
  );
}
