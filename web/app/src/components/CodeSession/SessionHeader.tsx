import type { SessionInfo, CliBackendInfo } from '../../hooks/useCodeSession';
import styles from './CodeSession.module.css';

interface SessionHeaderProps {
  session: SessionInfo | null;
  backendInfo: CliBackendInfo | null;
  onNewSession: () => void;
  onBack: () => void;
}

export function SessionHeader({ session, backendInfo, onNewSession, onBack }: SessionHeaderProps) {
  return (
    <div className={styles.header}>
      <div className={styles.headerLeft}>
        <button className={styles.headerBackBtn} onClick={onBack} aria-label="Back to sessions">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        {session ? (
          <>
            <span className={styles.headerTitle} title={session.name}>
              {session.name}
            </span>
            <span className={styles.headerBadge}>{session.model}</span>
            {session.totalCostUsd != null && backendInfo?.name === 'claude-cli' && (
              <span className={styles.headerCost}>${session.totalCostUsd.toFixed(4)}</span>
            )}
          </>
        ) : (
          <span className={styles.headerTitle}>Loading session...</span>
        )}
      </div>
      <div className={styles.headerActions}>
        <button className={`${styles.headerBtn} ${styles.headerBtnPrimary}`} onClick={onNewSession}>
          + New
        </button>
      </div>
    </div>
  );
}
