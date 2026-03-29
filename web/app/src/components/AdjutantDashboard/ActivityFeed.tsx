import styles from './ActivityFeed.module.css';

interface ActivityFeedProps {
  entries: string[];
}

interface ParsedEntry {
  timestamp: string;
  level: string;
  component: string;
  message: string;
}

/**
 * Try to parse a structured log line like:
 *   2026-03-28 14:02:19 [INFO] pulse — Synchronizing logistics schedules...
 *   2026-03-28 14:02:19 [WARN] review — Detected inconsistency...
 * Falls back to raw text if unparseable.
 */
function parseEntry(raw: string): ParsedEntry {
  // Pattern: optional timestamp, optional [LEVEL], optional component —, message
  const match = raw.match(
    /^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})?\s*\[?(\w+)\]?\s*(\w[\w.-]*)?\s*[—–-]?\s*(.+)$/
  );

  if (match) {
    const [, timestamp, level, component, message] = match;
    return {
      timestamp: timestamp?.trim() ?? '',
      level: (level ?? '').toUpperCase(),
      component: component ?? '',
      message: message?.trim() ?? raw,
    };
  }

  return { timestamp: '', level: '', component: '', message: raw };
}

function getStatusBadge(level: string): { label: string; className: string } | null {
  switch (level) {
    case 'INFO':
      return { label: 'CHECKED', className: styles.badgeChecked };
    case 'WARN':
    case 'WARNING':
      return { label: 'ESCALATED', className: styles.badgeEscalated };
    case 'ERROR':
      return { label: 'ERROR', className: styles.badgeError };
    case 'DEBUG':
      return { label: 'DEBUG', className: styles.badgeDebug };
    default:
      return null;
  }
}

function formatTime(timestamp: string): string {
  if (!timestamp) return '';
  // Extract HH:MM:SS from full timestamp
  const timePart = timestamp.split(' ')[1];
  return timePart ?? timestamp;
}

export function ActivityFeed({ entries }: ActivityFeedProps) {
  if (entries.length === 0) {
    return (
      <div className={styles.card}>
        <div className={styles.header}>
          <h2 className={styles.cardTitle}>Findings Feed</h2>
        </div>
        <p className={styles.empty}>No recent activity</p>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.cardTitle}>Findings Feed</h2>
        <span className={styles.liveTag}>Live Telemetry Stream</span>
      </div>

      <div className={styles.feed}>
        {entries.map((entry, index) => {
          const parsed = parseEntry(entry);
          const badge = getStatusBadge(parsed.level);

          return (
            <div key={index} className={styles.entry}>
              <div className={styles.entryIcon}>
                <div className={styles.dot} />
              </div>

              <div className={styles.entryContent}>
                {parsed.component && (
                  <div className={styles.entryMeta}>
                    <span className={styles.entryComponent}>{parsed.component}</span>
                  </div>
                )}
                <p className={styles.entryMessage}>{parsed.message}</p>
                {badge && (
                  <span className={`${styles.badge} ${badge.className}`}>
                    {badge.label}
                  </span>
                )}
              </div>

              {parsed.timestamp && (
                <span className={styles.entryTime}>{formatTime(parsed.timestamp)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
