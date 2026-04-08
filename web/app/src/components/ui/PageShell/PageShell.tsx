import type { ReactNode } from 'react';
import styles from './PageShell.module.css';

interface PageShellProps {
  sidebarOpen: boolean;
  /** Background element (e.g. <AnimatedBackground />) pinned to viewport */
  background?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function PageShell({ sidebarOpen, background, className, children }: PageShellProps) {
  const rootClass = `${styles.root} ${sidebarOpen ? styles.sidebarOpen : ''} ${className ?? ''}`;

  return (
    <div className={rootClass}>
      {background}
      <div className={styles.content}>
        {children}
      </div>
    </div>
  );
}
