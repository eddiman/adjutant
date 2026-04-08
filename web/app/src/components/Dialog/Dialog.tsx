import { useEffect, useCallback } from 'react';
import { Overlay } from '../ui';
import styles from './Dialog.module.css';

interface DialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'default';
  onConfirm: () => void;
  onCancel: () => void;
}

export function Dialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  onCancel,
}: DialogProps) {
  // Handle Enter key to confirm (Escape is handled by Overlay)
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.stopPropagation();
      onConfirm();
    }
  }, [onConfirm]);

  useEffect(() => {
    if (open) {
      window.addEventListener('keydown', handleKeyDown, { capture: true });
      return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <Overlay open={open} onClose={onCancel}>
      <div className={styles['dialog-container']}>
        <h2 className={styles['dialog-title']}>{title}</h2>
        <p className={styles['dialog-message']}>{message}</p>
        <div className={styles['dialog-actions']}>
          <button className={`${styles['dialog-button']} ${styles['dialog-button-cancel']}`} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            className={`${styles['dialog-button']} ${styles['dialog-button-confirm']} ${variant === 'danger' ? styles['dialog-button-danger'] : ''}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </Overlay>
  );
}
