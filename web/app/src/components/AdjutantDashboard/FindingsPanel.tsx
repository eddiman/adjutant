import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Card, Modal } from '../ui';
import type { InsightSummary } from '../../hooks/useAdjutant';
import styles from './FindingsPanel.module.css';

interface FindingsPanelProps {
  insights: InsightSummary[];
  loadingInsights: boolean;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return '';
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60_000);

    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin}m ago`;

    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return '';
  }
}

export function FindingsPanel({ insights, loadingInsights }: FindingsPanelProps) {
  const [selected, setSelected] = useState<InsightSummary | null>(null);
  const [selectedContent, setSelectedContent] = useState<string | null>(null);
  const [loadingContent, setLoadingContent] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);

  const pendingCount = insights.filter(i => i.status === 'pending').length;

  const openInsight = useCallback(async (insight: InsightSummary) => {
    setSelected(insight);
    setSelectedContent(null);
    setContentError(null);
    setLoadingContent(true);
    try {
      const res = await fetch(`/api/adjutant/insights/${insight.id}`);
      if (!res.ok) throw new Error('Failed to load insight');
      const data = await res.json();
      setSelectedContent(data.content ?? '');
    } catch (err) {
      console.error('Failed to load insight:', err);
      setContentError('Failed to load insight content.');
    } finally {
      setLoadingContent(false);
    }
  }, []);

  const closeInsight = useCallback(() => {
    setSelected(null);
    setSelectedContent(null);
    setContentError(null);
  }, []);

  const headerAction = pendingCount > 0
    ? <span className={styles.pendingBadge}>{pendingCount} pending</span>
    : <span className={styles.headerHint}>{insights.length} total</span>;

  return (
    <>
      <Card title="Findings" headerAction={headerAction} className={styles.card}>
        {loadingInsights ? (
          <p className={styles.empty}>Loading findings…</p>
        ) : insights.length === 0 ? (
          <p className={styles.empty}>No findings yet. Run a review to surface escalations.</p>
        ) : (
          <ul className={styles.list}>
            {insights.slice(0, 8).map(insight => (
              <li key={insight.id}>
                <button
                  type="button"
                  className={styles.item}
                  onClick={() => openInsight(insight)}
                >
                  <span
                    className={`${styles.statusDot} ${insight.status === 'pending' ? styles.dotPending : styles.dotSent}`}
                    aria-hidden
                  />
                  <span className={styles.itemBody}>
                    <span className={styles.itemTitle}>{insight.title}</span>
                    <span className={styles.itemMeta}>
                      <span className={styles.itemStatus}>{insight.status}</span>
                      {insight.timestamp && (
                        <>
                          <span aria-hidden>·</span>
                          <span>{formatTimestamp(insight.timestamp)}</span>
                        </>
                      )}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {insights.length > 8 && (
              <li className={styles.moreRow}>+{insights.length - 8} older</li>
            )}
          </ul>
        )}
      </Card>

      <Modal
        open={selected !== null}
        onClose={closeInsight}
        title={selected?.title ?? 'Finding'}
        width="44rem"
      >
        <div className={styles.modalBody}>
          {loadingContent && <p className={styles.empty}>Loading…</p>}
          {contentError && <p className={styles.error}>{contentError}</p>}
          {!loadingContent && !contentError && selectedContent !== null && (
            <div className={styles.markdown}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {selectedContent}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
