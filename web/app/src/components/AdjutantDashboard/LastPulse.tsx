import styles from './LastPulse.module.css';

interface LastHeartbeat {
  type?: string;
  timestamp?: string;
  kbs_checked?: string[];
  issues_found?: string[];
  escalated?: boolean;
}

interface LastPulseProps {
  heartbeat: LastHeartbeat | null | undefined;
}

function formatTimestamp(iso: string): string {
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60_000);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;

    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    // Older than 24h — show date
    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function LastPulse({ heartbeat }: LastPulseProps) {
  if (!heartbeat) {
    return (
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Last Pulse</h2>
        <p className={styles.empty}>No pulse data yet</p>
      </div>
    );
  }

  const { type, timestamp, kbs_checked, issues_found, escalated } = heartbeat;
  const title = type === 'review' ? 'Last Review' : 'Last Pulse';
  const issues = issues_found?.filter(Boolean) ?? [];

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>{title}</h2>

      {timestamp && (
        <p className={styles.timestamp}>{formatTimestamp(timestamp)}</p>
      )}

      {kbs_checked && kbs_checked.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionLabel}>KBs checked</div>
          <div className={styles.kbList}>
            {kbs_checked.map((kb) => (
              <span key={kb} className={styles.kbTag}>{kb}</span>
            ))}
          </div>
        </div>
      )}

      <div className={styles.section}>
        <div className={styles.sectionLabel}>Findings</div>
        {issues.length > 0 ? (
          <ul className={styles.issueList}>
            {issues.slice(0, 6).map((issue, i) => (
              <li key={i} className={styles.issue}>{issue}</li>
            ))}
            {issues.length > 6 && (
              <li className={styles.issue}>
                ... and {issues.length - 6} more
              </li>
            )}
          </ul>
        ) : (
          <p className={styles.noIssues}>No issues found</p>
        )}
      </div>

      {escalated && (
        <div className={styles.section}>
          <span className={styles.escalated}>
            <span>&#x26A0;&#xFE0F;</span>
            Escalated
          </span>
        </div>
      )}
    </div>
  );
}
