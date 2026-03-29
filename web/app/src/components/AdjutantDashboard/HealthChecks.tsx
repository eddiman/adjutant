import styles from './HealthChecks.module.css';

interface HealthChecksProps {
  health: {
    healthy: boolean;
    checks: {
      adjutantDirExists: boolean;
      configExists: boolean;
      cliExecutable: boolean;
      processRunning: boolean;
    };
  } | null;
  onRefresh: () => Promise<void>;
}

export function HealthChecks({ health, onRefresh }: HealthChecksProps) {
  if (!health) {
    return (
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Observer Telemetry</h3>
        <p className={styles.loading}>Loading...</p>
      </div>
    );
  }

  const checks = [
    {
      label: 'Adjutant Directory',
      status: health.checks.adjutantDirExists,
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      ),
    },
    {
      label: 'Config File',
      status: health.checks.configExists,
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      ),
    },
    {
      label: 'CLI Executable',
      status: health.checks.cliExecutable,
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4 17 10 11 4 5" />
          <line x1="12" y1="19" x2="20" y2="19" />
        </svg>
      ),
    },
    {
      label: 'Process Active',
      status: health.checks.processRunning,
      icon: (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 20V10" /><path d="M12 20V4" /><path d="M6 20v-6" />
        </svg>
      ),
    },
  ];

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h3 className={styles.cardTitle}>Observer Telemetry</h3>
        <button className={styles.refreshButton} onClick={onRefresh} title="Refresh">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
          </svg>
        </button>
      </div>

      <div className={styles.checksList}>
        {checks.map(check => (
          <div key={check.label} className={styles.checkRow}>
            <span className={styles.checkIcon}>{check.icon}</span>
            <span className={styles.checkLabel}>{check.label}</span>
            <span className={`${styles.checkValue} ${check.status ? styles.checkPass : styles.checkFail}`}>
              {check.status ? 'OK' : 'FAIL'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
