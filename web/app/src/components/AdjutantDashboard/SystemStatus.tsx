import styles from './SystemStatus.module.css';

interface SystemStatusProps {
  status: {
    mode: 'adjutant' | 'standalone';
    available: boolean;
    adjutantDir?: string;
    lifecycleState?: 'OPERATIONAL' | 'PAUSED' | 'KILLED' | 'STOPPED';
    processRunning?: boolean;
    listenerPid?: number;
  };
}

export function SystemStatus({ status }: SystemStatusProps) {
  const stateClass = {
    OPERATIONAL: styles.stateOperational,
    PAUSED: styles.statePaused,
    KILLED: styles.stateKilled,
    STOPPED: styles.stateStopped,
  }[status.lifecycleState ?? ''] ?? '';

  return (
    <div className={styles.hero}>
      <div className={styles.heroContent}>
        <span className={styles.statusLabel}>Status:</span>
        <h2 className={`${styles.stateText} ${stateClass}`}>
          {status.lifecycleState || 'UNKNOWN'}
        </h2>

        <div className={styles.badges}>
          <span className={styles.badge}>
            Backend: {status.mode === 'adjutant' ? 'Claude-CLI' : 'Standalone'}
          </span>
          <span className={`${styles.badge} ${status.processRunning ? styles.badgeActive : styles.badgeInactive}`}>
            Process: {status.processRunning ? 'Running' : 'Stopped'}
          </span>
        </div>
      </div>

      <div className={styles.heroVisual}>
        <div className={`${styles.orb} ${stateClass}`}>
          <div className={styles.orbInner} />
        </div>
      </div>
    </div>
  );
}
