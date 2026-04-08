import { Card } from '../ui';
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
      <Card title="Observation Summary" className={styles.card}>
        <p className={styles.empty}>No pulse data yet</p>
      </Card>
    );
  }

  const { type, timestamp, kbs_checked, issues_found, escalated } = heartbeat;
  const issues = issues_found?.filter(Boolean) ?? [];
  const kbCount = kbs_checked?.length ?? 0;

  // Build summary text
  let summaryText = '';
  if (type === 'review') {
    summaryText = `Last review completed${timestamp ? ` ${formatTimestamp(timestamp)}` : ''}. `;
  } else {
    summaryText = `Last pulse completed${timestamp ? ` ${formatTimestamp(timestamp)}` : ''}. `;
  }

  if (kbCount > 0) {
    summaryText += `${kbCount} knowledge base${kbCount !== 1 ? 's' : ''} checked. `;
  }

  if (issues.length > 0) {
    summaryText += `${issues.length} finding${issues.length !== 1 ? 's' : ''} detected.`;
  } else {
    summaryText += 'No significant deviations detected.';
  }

  return (
    <Card title="Observation Summary" className={styles.card}>
      <p className={styles.summary}>{summaryText}</p>

      {kbs_checked && kbs_checked.length > 0 && (
        <div className={styles.kbRow}>
          {kbs_checked.map((kb) => (
            <span key={kb} className={styles.kbTag}>{kb}</span>
          ))}
        </div>
      )}

      {issues.length > 0 && (
        <div className={styles.findings}>
          {issues.slice(0, 4).map((issue, i) => (
            <div key={i} className={styles.finding}>{issue}</div>
          ))}
          {issues.length > 4 && (
            <span className={styles.more}>+{issues.length - 4} more</span>
          )}
        </div>
      )}

      {escalated && (
        <div className={styles.escalated}>Escalated</div>
      )}
    </Card>
  );
}
