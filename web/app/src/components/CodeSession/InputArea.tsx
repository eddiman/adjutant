import { useState, useRef, useCallback, useEffect } from 'react';
import { SlashCommandPalette } from './SlashCommandPalette';
import { useSlashCommands } from '../../hooks/useSlashCommands';
import type { SlashCommand } from '../../hooks/useSlashCommands';
import styles from './InputArea.module.css';

interface InputAreaProps {
  onSend: (content: string) => void;
  onCancel: () => void;
  onSlashCommand: (command: SlashCommand) => void;
  isStreaming: boolean;
  disabled?: boolean;
  lastUserMessage?: string;
}

export function InputArea({
  onSend,
  onCancel,
  onSlashCommand,
  isStreaming,
  disabled,
  lastUserMessage,
}: InputAreaProps) {
  const [value, setValue] = useState('');
  const [showPalette, setShowPalette] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { filteredCommands, selectedIndex, moveUp, moveDown, resetSelection } = useSlashCommands();

  const filtered = filteredCommands(value);

  useEffect(() => {
    setShowPalette(value.startsWith('/') && filtered.length > 0 && !isStreaming);
  }, [value, filtered.length, isStreaming]);

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`;
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;

    if (trimmed.startsWith('/')) {
      const cmd = filtered.find(c => c.name === trimmed);
      if (cmd) {
        onSlashCommand(cmd);
        setValue('');
        autoResize();
        return;
      }
    }

    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, filtered, onSend, onSlashCommand, autoResize]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (showPalette) {
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        moveUp();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        moveDown(filtered.length - 1);
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const cmd = filtered[selectedIndex];
        if (cmd) {
          onSlashCommand(cmd);
          setValue('');
          setShowPalette(false);
          resetSelection();
        }
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowPalette(false);
        setValue('');
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }

    if (e.key === 'ArrowUp' && !value && lastUserMessage) {
      e.preventDefault();
      setValue(lastUserMessage);
    }
  }, [showPalette, value, lastUserMessage, handleSend, filtered, selectedIndex, moveUp, moveDown, resetSelection, onSlashCommand]);

  const handlePaletteSelect = useCallback((cmd: SlashCommand) => {
    onSlashCommand(cmd);
    setValue('');
    setShowPalette(false);
    resetSelection();
    textareaRef.current?.focus();
  }, [onSlashCommand, resetSelection]);

  return (
    <div className={styles.wrapper}>
      {showPalette && (
        <SlashCommandPalette
          commands={filtered}
          selectedIndex={selectedIndex}
          onSelect={handlePaletteSelect}
        />
      )}
      <div className={styles.inputCard}>
        <div className={styles.inputRow}>
          <textarea
            ref={textareaRef}
            className={styles.textarea}
            value={value}
            onChange={e => { setValue(e.target.value); autoResize(); }}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? 'Waiting for response...' : 'Ask anything...'}
            disabled={isStreaming || disabled}
            rows={1}
          />
          {isStreaming ? (
            <button className={styles.cancelBtn} onClick={onCancel}>
              Cancel
            </button>
          ) : (
            <button
              className={styles.sendBtn}
              onClick={handleSend}
              disabled={!value.trim() || disabled}
              aria-label="Send message"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
