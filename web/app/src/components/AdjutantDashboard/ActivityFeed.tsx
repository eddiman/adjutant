import styles from './ActivityFeed.module.css';

interface ActivityFeedProps {
  entries: string[];
}

export function ActivityFeed({ entries }: ActivityFeedProps) {
  if (entries.length === 0) {
    return (
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Recent Activity</h2>
        <p className={styles.empty}>No recent activity</p>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>
        Recent Activity <span className={styles.count}>({entries.length})</span>
      </h2>

      <div className={styles.feed}>
        {entries.map((entry, index) => (
          <div key={index} className={styles.entry}>
            <span className={styles.entryDot}>•</span>
            <span className={styles.entryText}>{entry}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
