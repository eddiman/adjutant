import type { ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps {
  title?: string;
  /** Element rendered in the header's right side (badge, button, tabs) */
  headerAction?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Card({ title, headerAction, className, children }: CardProps) {
  return (
    <div className={`${styles.card} ${className ?? ''}`}>
      {(title || headerAction) && (
        <div className={styles.header}>
          {title && <h3 className={styles.cardTitle}>{title}</h3>}
          {headerAction}
        </div>
      )}
      {children}
    </div>
  );
}
