import type { ReactNode, CSSProperties } from 'react';
import { Overlay } from '../Overlay';
import styles from './Modal.module.css';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Width override (CSS value), defaults to 25rem */
  width?: string;
  /** z-index layer for nested modals */
  layer?: 'dialog' | 'dialog-above';
  /** Footer content (action buttons) */
  footer?: ReactNode;
  children: ReactNode;
}

export function Modal({ open, onClose, title, width, layer, footer, children }: ModalProps) {
  const style: CSSProperties | undefined = width ? { width } : undefined;

  return (
    <Overlay open={open} onClose={onClose} layer={layer}>
      <div className={styles.modal} style={style}>
        <div className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className={styles.content}>
          {children}
        </div>
        {footer && (
          <div className={styles.footer}>
            {footer}
          </div>
        )}
      </div>
    </Overlay>
  );
}
