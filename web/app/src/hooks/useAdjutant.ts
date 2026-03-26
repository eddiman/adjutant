import { useCallback, useEffect, useRef, useState } from 'react';

export type LifecycleAction = 'pause' | 'resume' | 'pulse' | 'review';
export type ActionState = 'idle' | 'running' | 'success' | 'error';

interface ActiveOperation {
  action: string;
  started_at: string;
  pid: number;
  source: string;
}

interface LastHeartbeat {
  type: string;
  timestamp: string;
  kbs_checked: string[];
  issues_found?: string[];
  insights_sent?: number;
  recommendations?: string[];
  escalated?: boolean;
}

export interface AdjutantStatus {
  mode: 'adjutant' | 'standalone';
  available: boolean;
  adjutantDir?: string;
  lifecycleState?: 'OPERATIONAL' | 'PAUSED' | 'KILLED' | 'STOPPED';
  processRunning?: boolean;
  listenerPid?: number;
  activeOperation?: ActiveOperation | null;
  lastHeartbeat?: LastHeartbeat | null;
}

export interface Schedule {
  name: string;
  description: string;
  schedule: string;
  enabled: boolean;
  script?: string;
  log?: string;
  kb_name?: string;
  kb_operation?: string;
}

export interface Identity {
  soul: string;
  heart: string;
  registry: string;
}

export interface HealthStatus {
  healthy: boolean;
  checks: {
    adjutantDirExists: boolean;
    configExists: boolean;
    cliExecutable: boolean;
    processRunning: boolean;
  };
}

export interface AdjutantData {
  status: AdjutantStatus | null;
  schedules: Schedule[];
  identity: Identity | null;
  health: HealthStatus | null;
  journalEntries: string[];
  loading: boolean;
  error: string | null;
  actionStates: Record<LifecycleAction, ActionState>;
  fetchStatus: () => Promise<void>;
  fetchSchedules: () => Promise<void>;
  fetchHealth: () => Promise<void>;
  handleScheduleToggle: (name: string, enabled: boolean) => Promise<void>;
  handleScheduleRun: (name: string) => Promise<void>;
  runLifecycleAction: (action: LifecycleAction) => Promise<void>;
}

/** Polling interval when an operation is active (ms). */
const POLL_ACTIVE_MS = 3_000;
/** How long to show the "Done" state after an operation completes (ms). */
const SUCCESS_DISPLAY_MS = 4_000;

/**
 * Persistent hook for Adjutant dashboard data.
 *
 * Lives in AppContent so state survives route changes.
 * Fetches once on first mount, then polls /status to track active operations.
 * Button states are derived from Adjutant's filesystem state, not in-memory.
 */
export function useAdjutant(): AdjutantData {
  const [status, setStatus] = useState<AdjutantStatus | null>(null);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [journalEntries, setJournalEntries] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track which actions recently completed — for brief "Done" display
  const [recentlyCompleted, setRecentlyCompleted] = useState<Partial<Record<LifecycleAction, true>>>({});
  // Track which actions failed to trigger (HTTP POST failed)
  const [triggerErrors, setTriggerErrors] = useState<Partial<Record<LifecycleAction, true>>>({});

  const fetched = useRef(false);
  const pollRef = useRef<number | null>(null);
  const successTimers = useRef<Record<string, number>>({});
  // Track what was active on last poll to detect transitions
  const prevActiveAction = useRef<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/adjutant/status');
      if (!res.ok) throw new Error('Failed to fetch status');
      const data: AdjutantStatus = await res.json();

      // Detect operation completion: was active, now not
      const currentActive = data.activeOperation?.action ?? null;
      const prevActive = prevActiveAction.current;

      if (prevActive && !currentActive) {
        // Operation just completed — show "Done" briefly
        const completed = prevActive as LifecycleAction;
        setRecentlyCompleted(prev => ({ ...prev, [completed]: true }));

        // Clear the success display after a few seconds
        if (successTimers.current[completed]) {
          clearTimeout(successTimers.current[completed]);
        }
        successTimers.current[completed] = window.setTimeout(() => {
          setRecentlyCompleted(prev => {
            const next = { ...prev };
            delete next[completed];
            return next;
          });
          delete successTimers.current[completed];
        }, SUCCESS_DISPLAY_MS);
      }

      prevActiveAction.current = currentActive;
      setStatus(data);
    } catch (err) {
      console.error('Failed to fetch status:', err);
      setError('Failed to load Adjutant status');
    }
  }, []);

  const fetchSchedules = useCallback(async () => {
    try {
      const res = await fetch('/api/adjutant/schedules');
      if (!res.ok) throw new Error('Failed to fetch schedules');
      const data = await res.json();
      setSchedules(data.schedules || []);
    } catch (err) {
      console.error('Failed to fetch schedules:', err);
    }
  }, []);

  const fetchIdentity = useCallback(async () => {
    try {
      const res = await fetch('/api/adjutant/identity');
      if (!res.ok) throw new Error('Failed to fetch identity');
      const data = await res.json();
      setIdentity(data);
    } catch (err) {
      console.error('Failed to fetch identity:', err);
    }
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/adjutant/health');
      if (!res.ok) throw new Error('Failed to fetch health');
      const data = await res.json();
      setHealth(data);
    } catch (err) {
      console.error('Failed to fetch health:', err);
    }
  }, []);

  const fetchJournal = useCallback(async () => {
    try {
      const res = await fetch('/api/adjutant/journal/recent');
      if (!res.ok) throw new Error('Failed to fetch journal');
      const data = await res.json();
      setJournalEntries(data.entries || []);
    } catch (err) {
      console.error('Failed to fetch journal:', err);
    }
  }, []);

  // Fetch everything once on first mount
  useEffect(() => {
    if (fetched.current) return;
    fetched.current = true;

    const fetchAll = async () => {
      setLoading(true);
      setError(null);
      await Promise.all([
        fetchStatus(),
        fetchSchedules(),
        fetchIdentity(),
        fetchHealth(),
        fetchJournal(),
      ]);
      setLoading(false);
    };

    fetchAll();
  }, [fetchStatus, fetchSchedules, fetchIdentity, fetchHealth, fetchJournal]);

  // Poll /status ONLY while an operation is active — stop once it completes.
  // No idle polling. Initial state comes from the one-time fetch above.
  useEffect(() => {
    const isActive = !!status?.activeOperation;

    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    if (isActive) {
      pollRef.current = window.setInterval(() => {
        fetchStatus();
      }, POLL_ACTIVE_MS);
    }

    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [status?.activeOperation, fetchStatus]);

  // Cleanup success timers on unmount
  useEffect(() => {
    return () => {
      for (const timer of Object.values(successTimers.current)) {
        clearTimeout(timer);
      }
    };
  }, []);

  const handleScheduleToggle = useCallback(async (name: string, enabled: boolean) => {
    const res = await fetch('/api/adjutant/schedules/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, enabled }),
    });
    if (!res.ok) throw new Error('Failed to toggle schedule');
    await fetchSchedules();
  }, [fetchSchedules]);

  const handleScheduleRun = useCallback(async (name: string) => {
    const res = await fetch('/api/adjutant/schedules/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error('Failed to run schedule');
  }, []);

  const runLifecycleAction = useCallback(async (action: LifecycleAction) => {
    // Clear any previous error for this action
    setTriggerErrors(prev => {
      const next = { ...prev };
      delete next[action];
      return next;
    });

    try {
      const res = await fetch('/api/adjutant/lifecycle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      if (!res.ok) throw new Error(`Failed to ${action}`);

      // For pause/resume: refresh status immediately (they're synchronous).
      // For pulse/review: the detached process may not have written the
      // active_operation marker yet, so fetch once now and again after a
      // short delay.  The second fetch triggers the polling effect.
      await fetchStatus();
      if (action === 'pulse' || action === 'review') {
        window.setTimeout(() => { fetchStatus(); }, 1500);
      }
    } catch (err) {
      console.error(`Lifecycle action ${action} failed:`, err);
      setTriggerErrors(prev => ({ ...prev, [action]: true }));

      // Auto-clear error after 4s
      window.setTimeout(() => {
        setTriggerErrors(prev => {
          const next = { ...prev };
          delete next[action];
          return next;
        });
      }, 4000);
    }
  }, [fetchStatus]);

  // Derive actionStates from Adjutant's reported state
  const actionStates: Record<LifecycleAction, ActionState> = {
    pause: 'idle',
    resume: 'idle',
    pulse: 'idle',
    review: 'idle',
  };

  const activeAction = status?.activeOperation?.action;
  if (activeAction && activeAction in actionStates) {
    actionStates[activeAction as LifecycleAction] = 'running';
  }

  // Override with recently-completed (brief "Done" display)
  for (const action of Object.keys(recentlyCompleted) as LifecycleAction[]) {
    if (actionStates[action] !== 'running') {
      actionStates[action] = 'success';
    }
  }

  // Override with trigger errors
  for (const action of Object.keys(triggerErrors) as LifecycleAction[]) {
    if (actionStates[action] === 'idle') {
      actionStates[action] = 'error';
    }
  }

  return {
    status,
    schedules,
    identity,
    health,
    journalEntries,
    loading,
    error,
    actionStates,
    fetchStatus,
    fetchSchedules,
    fetchHealth,
    handleScheduleToggle,
    handleScheduleRun,
    runLifecycleAction,
  };
}
