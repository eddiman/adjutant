import { Card } from '../ui';
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
 * Parse Adjutant's `adj_log()` format:
 *   [HH:MM DD.MM.YYYY] [context] message
 *   [HH:MM DD.MM.YYYY] [context] ERROR: message
 *   [HH:MM DD.MM.YYYY] [context] WARNING: message
 *   [HH:MM DD.MM.YYYY] [context] DEBUG: message
 * Falls back to raw text if unparseable.
 */
function parseEntry(raw: string): ParsedEntry {
  const match = raw.match(
    /^\[(\d{2}:\d{2})\s+(\d{2}\.\d{2}\.\d{4})\]\s+\[([^\]]+)\]\s+(.+)$/
  );

  if (!match) {
    return { timestamp: '', level: '', component: '', message: raw };
  }

  const [, time, , component, body] = match;

  // Derive level from the message prefix
  let level = 'INFO';
  let message = body;
  if (body.startsWith('ERROR:')) {
    level = 'ERROR';
    message = body.slice(6).trim();
  } else if (body.startsWith('WARNING:')) {
    level = 'WARN';
    message = body.slice(8).trim();
  } else if (body.startsWith('DEBUG:')) {
    level = 'DEBUG';
    message = body.slice(6).trim();
  }

  return {
    timestamp: time,
    level,
    component,
    message,
  };
}

function getStatusBadge(level: string): { label: string; className: string } | null {
  switch (level) {
    case 'INFO':
      return { label: 'INFO', className: styles.badgeChecked };
    case 'WARN':
    case 'WARNING':
      return { label: 'WARN', className: styles.badgeEscalated };
    case 'ERROR':
      return { label: 'ERROR', className: styles.badgeError };
    case 'DEBUG':
      return { label: 'DEBUG', className: styles.badgeDebug };
    default:
      return null;
  }
}

function formatTime(timestamp: string): string {
  // Already HH:MM from the parser
  return timestamp;
}

export function ActivityFeed({ entries }: ActivityFeedProps) {
  if (entries.length === 0) {
    return (
      <Card title="Activity Log" className={styles.card}>
        <p className={styles.empty}>No recent activity</p>
      </Card>
    );
  }

  return (
    <Card title="Activity Log" headerAction={<span className={styles.liveTag}>Live Telemetry Stream</span>} className={styles.card}>
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
    </Card>
  );
}
