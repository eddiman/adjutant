import type { LifecycleAction, ActionState } from '../../hooks/useAdjutant';
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

  const getButtonContent = (action: LifecycleAction, icon: string, label: string) => {
    const state = actionStates[action];

    switch (state) {
      case 'running':
        return (
          <>
            <span className={`${styles.actionIcon} ${styles.spinning}`}>⟳</span>
            <span className={styles.actionLabel}>Running...</span>
          </>
        );
      case 'success':
        return (
          <>
            <span className={`${styles.actionIcon} ${styles.successIcon}`}>✓</span>
            <span className={`${styles.actionLabel} ${styles.successLabel}`}>Done</span>
          </>
        );
      case 'error':
        return (
          <>
            <span className={`${styles.actionIcon} ${styles.errorIcon}`}>✗</span>
            <span className={`${styles.actionLabel} ${styles.errorLabel}`}>Failed</span>
          </>
        );
      default:
        return (
          <>
            <span className={styles.actionIcon}>{icon}</span>
            <span className={styles.actionLabel}>{label}</span>
          </>
        );
    }
  };

  const getButtonClass = (action: LifecycleAction, baseClass: string) => {
    const state = actionStates[action];
    const classes = [styles.actionButton, baseClass];
    if (state === 'running') classes.push(styles.actionRunning);
    if (state === 'success') classes.push(styles.actionSuccess);
    if (state === 'error') classes.push(styles.actionError);
    return classes.join(' ');
  };

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>Quick Actions</h2>

      <div className={styles.actionsGrid}>
        {!isPaused && !isKilled && !isStopped && (
          <button
            className={getButtonClass('pause', styles.actionPause)}
            onClick={() => onAction('pause')}
            disabled={actionStates.pause === 'running'}
          >
            {getButtonContent('pause', '⏸', 'Pause')}
          </button>
        )}

        {isPaused && (
          <button
            className={getButtonClass('resume', styles.actionResume)}
            onClick={() => onAction('resume')}
            disabled={actionStates.resume === 'running'}
          >
            {getButtonContent('resume', '▶', 'Resume')}
          </button>
        )}

        <button
          className={getButtonClass('pulse', styles.actionPulse)}
          onClick={() => onAction('pulse')}
          disabled={actionStates.pulse === 'running'}
        >
          {getButtonContent('pulse', '💓', 'Pulse')}
        </button>

        <button
          className={getButtonClass('review', styles.actionReview)}
          onClick={() => onAction('review')}
          disabled={actionStates.review === 'running'}
        >
          {getButtonContent('review', '📋', 'Review')}
        </button>
      </div>
    </div>
  );
}
