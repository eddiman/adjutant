import { SystemStatus } from './SystemStatus';
import { SchedulesManager } from './SchedulesManager';
import { IdentityDisplay } from './IdentityDisplay';
import { QuickActions } from './QuickActions';
import { HealthChecks } from './HealthChecks';
import { ActivityFeed } from './ActivityFeed';
import { LastPulse } from './LastPulse';
import { FindingsPanel } from './FindingsPanel';
import { JournalPanel } from './JournalPanel';
import { AnimatedBackground } from '../Home/AnimatedBackground';
import { PageShell } from '../ui';
import type { AdjutantData } from '../../hooks/useAdjutant';
import styles from './AdjutantDashboard.module.css';

interface AdjutantDashboardProps {
  sidebarOpen?: boolean;
  data: AdjutantData;
}

export function AdjutantDashboard({ sidebarOpen = false, data }: AdjutantDashboardProps) {
  if (!data) return null;

  const {
    status,
    schedules,
    identity,
    health,
    logEntries,
    insights,
    loadingInsights,
    journalDays,
    loadingJournal,
    loading,
    error,
    fetchHealth,
    handleScheduleToggle,
    handleScheduleRun,
    actionStates,
    runLifecycleAction,
  } = data;

  if (loading) {
    return (
      <PageShell sidebarOpen={sidebarOpen} background={<AnimatedBackground />}>
        <p className={styles.loading}>Loading...</p>
      </PageShell>
    );
  }

  if (error || !status || !status.available) {
    return (
      <PageShell sidebarOpen={sidebarOpen} background={<AnimatedBackground />}>
        <header className={styles.topNav}>
          <h1 className={styles.logo}>Adjutant</h1>
        </header>
        <div className={styles.error}>
          <p>{error || 'Adjutant integration not available'}</p>
          <p className={styles.errorHint}>
            Make sure Adjutant is installed and the environment variable is set.
          </p>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell sidebarOpen={sidebarOpen} background={<AnimatedBackground />}>
      <header className={styles.topNav}>
        <h1 className={styles.logo}>Adjutant</h1>
      </header>

      <div className={styles.columns}>
        {/* Left: Hero status + Findings + Journal + Activity + Identity */}
        <div className={styles.mainColumn}>
          <SystemStatus status={status} />
          <FindingsPanel insights={insights} loadingInsights={loadingInsights} />
          <JournalPanel days={journalDays} loadingJournal={loadingJournal} />
          <ActivityFeed entries={logEntries} />
          <IdentityDisplay identity={identity} />
        </div>

        {/* Right: Telemetry, actions, pulse, schedules */}
        <div className={styles.sideColumn}>
          <HealthChecks health={health} onRefresh={fetchHealth} />
          <QuickActions
            lifecycleState={status.lifecycleState}
            actionStates={actionStates}
            onAction={runLifecycleAction}
          />
          <LastPulse heartbeat={status.lastHeartbeat} />
          <SchedulesManager
            schedules={schedules}
            onToggle={handleScheduleToggle}
            onRun={handleScheduleRun}
          />
        </div>
      </div>
    </PageShell>
  );
}
