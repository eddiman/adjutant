import { SystemStatus } from './SystemStatus';
import { SchedulesManager } from './SchedulesManager';
import { IdentityDisplay } from './IdentityDisplay';
import { QuickActions } from './QuickActions';
import { HealthChecks } from './HealthChecks';
import { ActivityFeed } from './ActivityFeed';
import { LastPulse } from './LastPulse';
import { AnimatedBackground } from '../Home/AnimatedBackground';
import type { AdjutantData } from '../../hooks/useAdjutant';
import styles from './AdjutantDashboard.module.css';

interface AdjutantDashboardProps {
  sidebarOpen?: boolean;
  data: AdjutantData;
}

export function AdjutantDashboard({ sidebarOpen = false, data }: AdjutantDashboardProps) {
  // Guard for HMR / undefined race conditions
  if (!data) return null;

  const {
    status,
    schedules,
    identity,
    health,
    journalEntries,
    loading,
    error,
    fetchHealth,
    handleScheduleToggle,
    handleScheduleRun,
    actionStates,
    runLifecycleAction,
  } = data;

  const dashboardClass = `${styles.dashboard} ${sidebarOpen ? styles.sidebarOpen : ''}`;

  if (loading) {
    return (
      <div className={dashboardClass}>
        <AnimatedBackground />
        <div className={styles.content}>
          <h1 className={styles.title}>Adjutant Dashboard</h1>
          <p className={styles.loading}>Loading...</p>
        </div>
      </div>
    );
  }

  if (error || !status || !status.available) {
    return (
      <div className={dashboardClass}>
        <AnimatedBackground />
        <div className={styles.content}>
          <h1 className={styles.title}>Adjutant Dashboard</h1>
          <div className={styles.error}>
            <p>{error || 'Adjutant integration not available'}</p>
            <p className={styles.errorHint}>
              Make sure Adjutant is installed and the environment variable is set.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={dashboardClass}>
      <AnimatedBackground />
      <div className={styles.content}>
        <header className={styles.header}>
          <h1 className={styles.title}>
            <span className={styles.titleBracket}>&lt;</span>
            Adjutant
            <span className={styles.titleBracket}>&gt;</span>
          </h1>
          <p className={styles.subtitle}>Agent Control Center</p>
        </header>

        <div className={styles.grid}>
          <SystemStatus status={status} />
          <QuickActions
            lifecycleState={status.lifecycleState}
            actionStates={actionStates}
            onAction={runLifecycleAction}
          />
          <LastPulse heartbeat={status.lastHeartbeat} />
          <HealthChecks health={health} onRefresh={fetchHealth} />
          <SchedulesManager
            schedules={schedules}
            onToggle={handleScheduleToggle}
            onRun={handleScheduleRun}
          />
          <IdentityDisplay identity={identity} />
          <ActivityFeed entries={journalEntries} />
        </div>
      </div>
    </div>
  );
}
