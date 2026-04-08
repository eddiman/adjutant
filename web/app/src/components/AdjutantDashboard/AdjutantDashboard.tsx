import { SystemStatus } from './SystemStatus';
import { SchedulesManager } from './SchedulesManager';
import { IdentityDisplay } from './IdentityDisplay';
import { QuickActions } from './QuickActions';
import { HealthChecks } from './HealthChecks';
import { ActivityFeed } from './ActivityFeed';
import { LastPulse } from './LastPulse';
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
    journalEntries,
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
        <nav className={styles.topNav}>
          <h1 className={styles.logo}>Adjutant</h1>
        </nav>
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
      <nav className={styles.topNav}>
        <h1 className={styles.logo}>Adjutant</h1>
        <div className={styles.navTabs}>
          <button className={`${styles.navTab} ${styles.navTabActive}`}>Pulse</button>
          <button className={styles.navTab}>Schedules</button>
          <button className={styles.navTab}>System Logs</button>
        </div>
        <div className={styles.navSpacer} />
        <div className={styles.navIcons}>
          <button className={styles.navIcon} title="Settings">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
          </button>
        </div>
      </nav>

      <div className={styles.columns}>
        {/* Left: Hero status + Findings feed + Identity */}
        <div className={styles.mainColumn}>
          <SystemStatus status={status} />
          <ActivityFeed entries={journalEntries} />
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
