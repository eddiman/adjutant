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
        <h2 className={styles.cardTitle}>Health Checks</h2>
        <p className={styles.loading}>Loading...</p>
      </div>
    );
  }

  const checks = [
    { label: 'Adjutant Directory', status: health.checks.adjutantDirExists },
    { label: 'Config File', status: health.checks.configExists },
    { label: 'CLI Executable', status: health.checks.cliExecutable },
    { label: 'Process Running', status: health.checks.processRunning },
  ];

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.cardTitle}>Health Checks</h2>
        <button className={styles.refreshButton} onClick={onRefresh} title="Refresh health checks">
          ↻
        </button>
      </div>

      <div className={styles.overallStatus}>
        <span className={`${styles.statusIndicator} ${health.healthy ? styles.statusHealthy : styles.statusUnhealthy}`}>
          {health.healthy ? '●' : '●'}
        </span>
        <span className={styles.statusText}>
          {health.healthy ? 'All systems operational' : 'Issues detected'}
        </span>
      </div>

      <div className={styles.checksList}>
        {checks.map(check => (
          <div key={check.label} className={styles.checkItem}>
            <span className={styles.checkLabel}>{check.label}</span>
            <span className={`${styles.checkStatus} ${check.status ? styles.checkPass : styles.checkFail}`}>
              {check.status ? '✓' : '✗'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
