import { useState, useEffect } from 'react';
import styles from './Canvas.module.css';

interface CanvasLoaderProps {
  isLoading: boolean;
  onTransitionComplete: () => void;
}

export function CanvasLoader({ isLoading, onTransitionComplete }: CanvasLoaderProps) {
  const [phase, setPhase] = useState<'loading' | 'exiting' | 'done'>('loading');

  useEffect(() => {
    if (!isLoading && phase === 'loading') {
      // Start exit animation
      setPhase('exiting');
      
      // After exit animation completes, signal done
      const timer = setTimeout(() => {
        setPhase('done');
        onTransitionComplete();
      }, 500); // Match exit animation duration

      return () => clearTimeout(timer);
    }
  }, [isLoading, phase, onTransitionComplete]);

  if (phase === 'done') {
    return null;
  }

  const containerClass = [
    styles['canvas-loader'],
    phase === 'exiting' ? styles['canvas-loader--exiting'] : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={containerClass}>
      <div className={styles['canvas-loader-shape']}>
        <div className={styles['canvas-loader-morph']} />
      </div>
      <p className={styles['canvas-loader-text']}>Loading notes...</p>
    </div>
  );
}
