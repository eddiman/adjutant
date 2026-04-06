import { useEffect, useState } from 'react';
import { isTouchDevice } from '../../utils/platform.js';
import styles from './GhostNote.module.css';

interface GhostNoteProps {
  visible: boolean;
}

export function GhostNote({ visible }: GhostNoteProps) {
  const [position, setPosition] = useState(() => ({
    x: window.innerWidth,
    y: window.innerHeight,
  }));
  const isTouch = isTouchDevice();
  const posOffset = 25;

  // Track mouse position on desktop
  useEffect(() => {
    if (!visible || isTouch) return;

    const handleMouseMove = (e: MouseEvent) => {
      setPosition({ x: e.clientX - posOffset, y: e.clientY - posOffset });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [visible, isTouch]);

  // Don't render on touch devices or when not visible
  if (!visible || isTouch) return null;

  const offsetX = 20;
  const offsetY = 20;

  return (
    <div
      className={styles['ghost-note']}
      style={{
        left: position.x + offsetX,
        top: position.y + offsetY,
      }}
    >
      <div className={styles['ghost-note-lines']}>
        <span />
        <span />
        <span />
      </div>
      <p className={styles['ghost-note-hint']}>Click to place</p>
    </div>
  );
}
