import { useState } from 'react';
import styles from './SchedulesManager.module.css';

/**
 * Convert a cron expression to a human-readable string.
 * Handles common patterns used in adjutant.yaml schedules.
 */
function cronToHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return cron;

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;

  const formatTime = (h: string, m: string): string => {
    const pad = (n: string) => n.padStart(2, '0');
    if (h.includes(',')) {
      return h.split(',').map(hr => `${pad(hr)}:${pad(m)}`).join(', ');
    }
    return `${pad(h)}:${pad(m)}`;
  };

  const describeDays = (dow: string): string => {
    if (dow === '*') return '';
    if (dow === '1-5') return 'weekdays';
    if (dow === '0,6' || dow === '6,0') return 'weekends';
    if (dow === '0') return 'Sundays';
    if (dow === '1') return 'Mondays';
    if (dow === '2') return 'Tuesdays';
    if (dow === '3') return 'Wednesdays';
    if (dow === '4') return 'Thursdays';
    if (dow === '5') return 'Fridays';
    if (dow === '6') return 'Saturdays';
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    if (dow.includes(',')) {
      return dow.split(',').map(d => dayNames[parseInt(d)] || d).join(', ');
    }
    if (dow.includes('-')) {
      const [start, end] = dow.split('-');
      return `${dayNames[parseInt(start)]}–${dayNames[parseInt(end)]}`;
    }
    return dow;
  };

  // Every minute
  if (minute === '*' && hour === '*') return 'Every minute';

  // Hourly
  if (minute !== '*' && hour === '*') {
    const days = describeDays(dayOfWeek);
    const base = `Every hour at :${minute.padStart(2, '0')}`;
    return days ? `${base}, ${days}` : base;
  }

  // Specific times
  if (minute !== '*' && hour !== '*' && dayOfMonth === '*' && month === '*') {
    const time = formatTime(hour, minute);
    const days = describeDays(dayOfWeek);

    if (hour.includes(',')) {
      // Multiple times per day
      const times = hour.split(',').map(h => formatTime(h, minute));
      if (days) return `${days} at ${times.join(', ')}`;
      return `Daily at ${times.join(', ')}`;
    }

    if (days) return `${days.charAt(0).toUpperCase() + days.slice(1)} at ${time}`;
    return `Daily at ${time}`;
  }

  return cron;
}

interface Schedule {
  name: string;
  description: string;
  schedule: string;
  enabled: boolean;
  script?: string;
  log?: string;
  kb_name?: string;
  kb_operation?: string;
}

interface SchedulesManagerProps {
  schedules: Schedule[];
  onToggle: (name: string, enabled: boolean) => Promise<void>;
  onRun: (name: string) => Promise<void>;
}

export function SchedulesManager({ schedules, onToggle, onRun }: SchedulesManagerProps) {
  const [expandedSchedule, setExpandedSchedule] = useState<string | null>(null);

  const handleToggle = async (name: string, currentEnabled: boolean) => {
    await onToggle(name, !currentEnabled);
  };

  const handleRun = async (name: string) => {
    if (confirm(`Run schedule "${name}" now?`)) {
      await onRun(name);
    }
  };

  const toggleExpand = (name: string) => {
    setExpandedSchedule(prev => prev === name ? null : name);
  };

  if (schedules.length === 0) {
    return (
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>Schedules</h2>
        <p className={styles.empty}>No schedules configured</p>
      </div>
    );
  }

  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>
        Schedules <span className={styles.count}>({schedules.length})</span>
      </h2>

      <div className={styles.schedulesList}>
        {schedules.map(schedule => (
          <div key={schedule.name} className={styles.scheduleItem}>
            <div className={styles.scheduleHeader} onClick={() => toggleExpand(schedule.name)}>
              <div className={styles.scheduleInfo}>
                <h3 className={styles.scheduleName}>{schedule.name}</h3>
                <p className={styles.scheduleDescription}>{schedule.description}</p>
                <span className={styles.scheduleCron} title={schedule.schedule}>
                  {cronToHuman(schedule.schedule)}
                </span>
              </div>
              <div className={styles.scheduleStatus}>
                <span className={`${styles.statusBadge} ${schedule.enabled ? styles.statusEnabled : styles.statusDisabled}`}>
                  {schedule.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            </div>

            {expandedSchedule === schedule.name && (
              <div className={styles.scheduleDetails}>
                <div className={styles.detailsGrid}>
                  {schedule.kb_name && (
                    <>
                      <span className={styles.detailLabel}>KB:</span>
                      <span className={styles.detailValue}>{schedule.kb_name}</span>
                      <span className={styles.detailLabel}>Operation:</span>
                      <span className={styles.detailValue}>{schedule.kb_operation}</span>
                    </>
                  )}
                  {schedule.script && (
                    <>
                      <span className={styles.detailLabel}>Script:</span>
                      <span className={styles.detailValue}>{schedule.script}</span>
                    </>
                  )}
                  {schedule.log && (
                    <>
                      <span className={styles.detailLabel}>Log:</span>
                      <span className={styles.detailValue}>{schedule.log}</span>
                    </>
                  )}
                </div>

                <div className={styles.scheduleActions}>
                  <button
                    className={styles.actionButton}
                    onClick={() => handleToggle(schedule.name, schedule.enabled)}
                  >
                    {schedule.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    className={`${styles.actionButton} ${styles.actionButtonPrimary}`}
                    onClick={() => handleRun(schedule.name)}
                  >
                    Run Now
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
