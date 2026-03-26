import { memo } from 'react';
import { useViewport } from '@xyflow/react';
import styles from './SnapGuides.module.css';

export interface GuideLine {
  type: 'vertical' | 'horizontal';
  position: number; // x for vertical, y for horizontal
  start: number;    // y start for vertical, x start for horizontal
  end: number;      // y end for vertical, x end for horizontal
}

interface SnapGuidesProps {
  guides: GuideLine[];
}

export const SnapGuides = memo(function SnapGuides({ guides }: SnapGuidesProps) {
  const { x: vpX, y: vpY, zoom } = useViewport();

  if (guides.length === 0) return null;

  // Transform flow coordinates to screen coordinates
  const toScreen = (flowX: number, flowY: number) => ({
    x: flowX * zoom + vpX,
    y: flowY * zoom + vpY,
  });

  return (
    <svg className={styles['snap-guides']}>
      {guides.map((guide, index) => {
        if (guide.type === 'vertical') {
          const start = toScreen(guide.position, guide.start);
          const end = toScreen(guide.position, guide.end);
          return (
            <line
              key={index}
              className={styles['snap-guide-line']}
              x1={start.x}
              y1={start.y}
              x2={end.x}
              y2={end.y}
            />
          );
        } else {
          const start = toScreen(guide.start, guide.position);
          const end = toScreen(guide.end, guide.position);
          return (
            <line
              key={index}
              className={styles['snap-guide-line']}
              x1={start.x}
              y1={start.y}
              x2={end.x}
              y2={end.y}
            />
          );
        }
      })}
    </svg>
  );
});
