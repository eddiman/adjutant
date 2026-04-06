import styles from './CodeSession.module.css';

interface StatusBarProps {
  cwd: string;
  backendName: string | null;
  connected: boolean;
  reconnecting: boolean;
}

export function StatusBar({ cwd, backendName, connected, reconnecting }: StatusBarProps) {
  return (
    <div className={styles.statusBar}>
      <span className={styles.statusCwd}>{cwd}</span>
      <div className={styles.statusRight}>
        {backendName && <span>{backendName}</span>}
        <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
          <span
            className={styles.statusDot}
            style={{
              background: connected ? '#2ecc71' : reconnecting ? '#e6a23c' : '#f56c6c',
            }}
          />
          {connected ? 'Connected' : reconnecting ? 'Reconnecting...' : 'Disconnected'}
        </span>
      </div>
    </div>
  );
}
