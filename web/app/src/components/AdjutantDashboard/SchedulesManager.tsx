import { useState } from 'react';
import { Card } from '../ui';
import styles from './SchedulesManager.module.css';

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
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    if (/^\d$/.test(dow)) return dayNames[parseInt(dow)] + 's';
    if (dow.includes(',')) {
      return dow.split(',').map(d => dayNames[parseInt(d)] || d).join(', ');
    }
    if (dow.includes('-')) {
      const [start, end] = dow.split('-');
      return `${dayNames[parseInt(start)]}–${dayNames[parseInt(end)]}`;
    }
    return dow;
  };

  if (minute === '*' && hour === '*') return 'Every minute';

  if (minute !== '*' && hour === '*') {
    const days = describeDays(dayOfWeek);
    const base = `Every hour at :${minute.padStart(2, '0')}`;
    return days ? `${base}, ${days}` : base;
  }

  if (minute !== '*' && hour !== '*' && dayOfMonth === '*' && month === '*') {
    const time = formatTime(hour, minute);
    const days = describeDays(dayOfWeek);

    if (hour.includes(',')) {
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
      <Card title="Schedules" className={styles.card}>
        <p className={styles.empty}>No schedules configured</p>
      </Card>
    );
  }

  return (
    <Card title="Schedules" headerAction={<span className={styles.count}>({schedules.length})</span>} className={styles.card}>
      <div className={styles.schedulesList}>
        {schedules.map(schedule => (
          <div key={schedule.name} className={styles.scheduleItem}>
            <div className={styles.scheduleHeader} onClick={() => toggleExpand(schedule.name)}>
              <div className={styles.scheduleInfo}>
                <div className={styles.scheduleNameRow}>
                  <span className={styles.scheduleName}>{schedule.name}</span>
                  <span className={`${styles.statusDot} ${schedule.enabled ? styles.dotEnabled : styles.dotDisabled}`} />
                </div>
                <span className={styles.scheduleCron}>{cronToHuman(schedule.schedule)}</span>
              </div>
            </div>

            {expandedSchedule === schedule.name && (
              <div className={styles.scheduleDetails}>
                <p className={styles.scheduleDescription}>{schedule.description}</p>

                {schedule.kb_name && (
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>KB</span>
                    <span className={styles.detailValue}>{schedule.kb_name}</span>
                  </div>
                )}

                <div className={styles.scheduleActions}>
                  <button
                    className={styles.actionButton}
                    onClick={() => handleToggle(schedule.name, schedule.enabled)}
                  >
                    {schedule.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    className={`${styles.actionButton} ${styles.actionPrimary}`}
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
    </Card>
  );
}
