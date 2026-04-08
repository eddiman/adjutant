import { useEffect, useCallback, type ReactNode } from 'react';
import styles from './Overlay.module.css';

interface OverlayProps {
  open: boolean;
  onClose: () => void;
  /** z-index layer — 'dialog-above' renders above other dialogs (e.g. nested modals) */
  layer?: 'dialog' | 'dialog-above';
  children: ReactNode;
}

export function Overlay({ open, onClose, layer = 'dialog', children }: OverlayProps) {
  const handleEscape = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
    }
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    window.addEventListener('keydown', handleEscape, { capture: true });
    return () => window.removeEventListener('keydown', handleEscape, { capture: true });
  }, [open, handleEscape]);

  if (!open) return null;

  const className = `${styles.overlay} ${layer === 'dialog-above' ? styles.overlayAbove : ''}`;

  return (
    <div className={className} onClick={onClose}>
      <div onClick={e => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}
