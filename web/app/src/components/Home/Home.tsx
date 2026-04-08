import { useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatedBackground } from './AnimatedBackground';
import styles from './Home.module.css';

interface HomeProps {
  kbs: { name: string }[];
  loadingKbs: boolean;
  kbRootConfigured: boolean;
  onKbSelect: (kbName: string) => void;
  onNoteSelect: (note: { kb: string; path: string }) => void;
  onSettingsClick: () => void;
  searchNotes: (kb: string, query: string) => Promise<unknown[]>;
  searching: boolean;
}

export function Home({
  kbRootConfigured,
  onSettingsClick,
}: HomeProps) {
  const navigate = useNavigate();
  const [message, setMessage] = useState('');
  const [phase, setPhase] = useState<'idle' | 'animating' | 'done'>('idle');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  const handleSend = useCallback(async () => {
    if (!message.trim() || phase !== 'idle') return;

    // Store message for chat to pick up
    sessionStorage.setItem('adjutant-pending-message', message.trim());

    // Phase 1: animate prompt to bottom
    setPhase('animating');

    // Fetch adjutant dir while animation plays
    try {
      const statusRes = await fetch('/api/adjutant/status');
      const statusData = await statusRes.json();
      const cwd = statusData.adjutantDir || '/';
      sessionStorage.setItem('adjutant-pending-cwd', cwd);
    } catch {
      // Fallback
    }

    // Phase 2: after animation completes, navigate
    setTimeout(() => {
      setPhase('done');
      navigate('/chat');
    }, 500);
  }, [message, phase, navigate]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  if (!kbRootConfigured) {
    return (
      <div className={styles.home}>
        <AnimatedBackground />
        <div className={`${styles.content} ${styles.centered}`}>
          <h1 className={styles.title}>Adjutant</h1>
          <p className={styles.subtitle}>Your personal AI assistant</p>
          <div className={styles.setupCard}>
            <p className={styles.setupText}>No knowledge base directory configured.</p>
            <button className={styles.setupButton} onClick={onSettingsClick}>
              Configure KB Root
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isAnimating = phase === 'animating';

  return (
    <div className={styles.home}>
      <AnimatedBackground />

      {/* Title + subtitle — fades out when animating */}
      <div className={`${styles.titleBlock} ${isAnimating ? styles.titleHidden : ''}`}>
        <h1 className={styles.title}>Adjutant</h1>
        <p className={styles.subtitle}>Your personal AI assistant</p>
      </div>

      {/* Prompt card — centered normally, slides to bottom when animating */}
      <div className={`${styles.promptWrapper} ${isAnimating ? styles.promptDocked : ''}`}>
        <div className={styles.promptCard}>
          <div className={styles.promptInner}>
            <textarea
              ref={textareaRef}
              className={styles.promptInput}
              placeholder="Ask anything..."
              value={message}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={phase !== 'idle'}
            />
            <button
              className={`${styles.sendButton} ${message.trim() && phase === 'idle' ? styles.sendButtonVisible : ''}`}
              onClick={handleSend}
              aria-label="Send message"
              tabIndex={message.trim() ? 0 : -1}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Hint — fades out */}
      <p className={`${styles.hint} ${isAnimating ? styles.hintHidden : ''}`}>
        Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}
