import type { LifecycleAction, ActionState } from '../../hooks/useAdjutant';
import { Card } from '../ui';
import styles from './QuickActions.module.css';

interface QuickActionsProps {
  lifecycleState?: 'OPERATIONAL' | 'PAUSED' | 'KILLED' | 'STOPPED';
  actionStates: Record<LifecycleAction, ActionState>;
  onAction: (action: LifecycleAction) => Promise<void>;
}

export function QuickActions({ lifecycleState, actionStates, onAction }: QuickActionsProps) {
  const isPaused = lifecycleState === 'PAUSED';
  const isKilled = lifecycleState === 'KILLED';
  const isStopped = lifecycleState === 'STOPPED';

  const renderButton = (action: LifecycleAction, label: string, variant: string) => {
    const state = actionStates[action];
    const isRunning = state === 'running';
    const isSuccess = state === 'success';
    const isError = state === 'error';

    let displayLabel = label;
    let stateClass = '';

    if (isRunning) {
      displayLabel = 'Running...';
      stateClass = styles.running;
    } else if (isSuccess) {
      displayLabel = 'Done';
      stateClass = styles.success;
    } else if (isError) {
      displayLabel = 'Failed';
      stateClass = styles.error;
    }

    return (
      <button
        className={`${styles.actionButton} ${styles[variant] ?? ''} ${stateClass}`}
        onClick={() => onAction(action)}
        disabled={isRunning}
      >
        {isRunning && <span className={styles.spinner} />}
        {displayLabel}
      </button>
    );
  };

  return (
    <Card title="Quick Actions" className={styles.card}>
      <div className={styles.actions}>
        {renderButton('review', 'Review Findings', 'primary')}

        <div className={styles.row}>
          {!isPaused && !isKilled && !isStopped && (
            renderButton('pause', 'Pause', 'secondary')
          )}
          {isPaused && (
            renderButton('resume', 'Resume', 'secondary')
          )}
          {renderButton('pulse', 'Pulse', 'secondary')}
        </div>
      </div>
    </Card>
  );
}
