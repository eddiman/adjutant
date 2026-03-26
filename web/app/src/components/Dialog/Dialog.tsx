import { useEffect, useCallback } from 'react';
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
  // Handle Escape key to cancel
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onCancel();
    } else if (e.key === 'Enter') {
      e.stopPropagation();
      onConfirm();
    }
  }, [onCancel, onConfirm]);

  useEffect(() => {
    if (open) {
      window.addEventListener('keydown', handleKeyDown, { capture: true });
      return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
    }
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className={styles['dialog-overlay']} onClick={onCancel}>
      <div className={styles['dialog-container']} onClick={e => e.stopPropagation()}>
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
    </div>
  );
}
