import { useEffect, useState } from 'react';
import { isTouchDevice } from '../../utils/platform.js';
import styles from './GhostSticky.module.css';

interface GhostStickyProps {
  visible: boolean;
}

export function GhostSticky({ visible }: GhostStickyProps) {
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

  // Offset to position cursor at top-left corner of ghost
  const offsetX = 20;
  const offsetY = 20;

  return (
    <div
      className={styles['ghost-sticky']}
      style={{
        left: position.x + offsetX,
        top: position.y + offsetY,
      }}
    >
      <p className={styles['ghost-sticky-hint']}>Click to place</p>
    </div>
  );
}
