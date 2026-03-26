import { useState } from 'react';
import styles from './IdentityDisplay.module.css';

interface IdentityDisplayProps {
  identity: {
    soul: string;
    heart: string;
    registry: string;
  } | null;
}

type IdentityTab = 'soul' | 'heart' | 'registry';

export function IdentityDisplay({ identity }: IdentityDisplayProps) {
  const [activeTab, setActiveTab] = useState<IdentityTab>('soul');

  if (!identity) {
    return (
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Identity</h2>
        <p className={styles.loading}>Loading...</p>
      </div>
    );
  }

  const hasAnyContent = identity.soul || identity.heart || identity.registry;

  if (!hasAnyContent) {
    return (
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Identity</h2>
        <p className={styles.empty}>No identity files found</p>
      </div>
    );
  }

  const getContent = () => {
    switch (activeTab) {
      case 'soul':
        return identity.soul || 'No soul.md found';
      case 'heart':
        return identity.heart || 'No heart.md found';
      case 'registry':
        return identity.registry || 'No registry.md found';
    }
  };

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>Identity</h2>

      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'soul' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('soul')}
        >
          Soul
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'heart' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('heart')}
        >
          Heart
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'registry' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('registry')}
        >
          Registry
        </button>
      </div>

      <div className={styles.content}>
        <pre className={styles.excerpt}>{getContent()}</pre>
      </div>
    </div>
  );
}
