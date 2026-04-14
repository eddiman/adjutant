import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, Modal } from '../ui';
import type { JournalDaySummary } from '../../hooks/useAdjutant';
import styles from './JournalPanel.module.css';

interface JournalPanelProps {
  days: JournalDaySummary[];
  loadingJournal: boolean;
}

function formatDate(date: string): string {
  // Pretty-print YYYY-MM-DD relative to today
  try {
    const d = new Date(date + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffDays = Math.round((today.getTime() - d.getTime()) / 86_400_000);

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;

    return d.toLocaleDateString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return date;
  }
}

export function JournalPanel({ days, loadingJournal }: JournalPanelProps) {
  const [selected, setSelected] = useState<JournalDaySummary | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  const openDay = useCallback(async (day: JournalDaySummary) => {
    setSelected(day);
    setContent(null);
    setContentError(null);
    setLoadingContent(true);
    try {
      const res = await fetch(`/api/adjutant/journal/day/${day.date}`);
      if (!res.ok) throw new Error('Failed to load journal entry');
      const data = await res.json();
      setContent(data.content ?? '');
    } catch (err) {
      console.error('Failed to load journal entry:', err);
      setContentError('Failed to load journal entry.');
    } finally {
      setLoadingContent(false);
    }
  }, []);

  const closeDay = useCallback(() => {
    setSelected(null);
    setContent(null);
    setContentError(null);
  }, []);

  const headerAction = days.length > 0
    ? <span className={styles.headerHint}>{days.length} days</span>
    : null;

  return (
    <>
      <Card title="Journal" headerAction={headerAction} className={styles.card}>
        {loadingJournal ? (
          <p className={styles.empty}>Loading journal…</p>
        ) : days.length === 0 ? (
          <p className={styles.empty}>No journal entries yet. The journal fills up as pulses and reviews run.</p>
        ) : (
          <ul className={styles.list}>
            {days.slice(0, 6).map(day => (
              <li key={day.date}>
                <button
                  type="button"
                  className={styles.item}
                  onClick={() => openDay(day)}
                >
                  <span className={styles.itemDate}>{formatDate(day.date)}</span>
                  <span className={styles.itemBody}>
                    {day.preview && <span className={styles.itemPreview}>{day.preview}</span>}
                    <span className={styles.itemMeta}>
                      {day.entryCount} {day.entryCount === 1 ? 'entry' : 'entries'}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {days.length > 6 && (
              <li className={styles.moreRow}>+{days.length - 6} older</li>
            )}
          </ul>
        )}
      </Card>

      <Modal
        open={selected !== null}
        onClose={closeDay}
        title={selected ? formatDate(selected.date) : 'Journal'}
        width="44rem"
      >
        <div className={styles.modalBody}>
          {loadingContent && <p className={styles.empty}>Loading…</p>}
          {contentError && <p className={styles.error}>{contentError}</p>}
          {!loadingContent && !contentError && content !== null && (
            <div className={styles.markdown}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
