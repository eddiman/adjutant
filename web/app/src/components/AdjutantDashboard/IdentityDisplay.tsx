import { useState } from 'react';
import { Card } from '../ui';
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
      <Card title="Identity" className={styles.card}>
        <p className={styles.loading}>Loading...</p>
      </Card>
    );
  }

  const hasAnyContent = identity.soul || identity.heart || identity.registry;

  if (!hasAnyContent) {
    return (
      <Card title="Identity" className={styles.card}>
        <p className={styles.empty}>No identity files found</p>
      </Card>
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
    <Card
      title="Identity"
      headerAction={
        <div className={styles.tabs}>
          {(['soul', 'heart', 'registry'] as const).map(tab => (
            <button
              key={tab}
              className={`${styles.tab} ${activeTab === tab ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>
      }
      className={styles.card}
    >
      <div className={styles.content}>
        <pre className={styles.excerpt}>{getContent()}</pre>
      </div>
    </Card>
  );
}
