import { useMemo } from "react";
import { Background, BackgroundVariant, useViewport } from "@xyflow/react";

/**
 * Adaptive background that adjusts grid density based on zoom level.
 * At low zoom, the grid uses larger gaps to remain visible.
 * At high zoom, the grid uses smaller gaps for precision.
 */
export function AdaptiveBackground() {
  const { zoom } = useViewport();

  const { gap, size } = useMemo(() => {
    // Define zoom breakpoints and corresponding grid settings
    if (zoom < 0.15) {
      // Very zoomed out - large sparse grid
      return { gap: 100, size: 8 };
    } else if (zoom < 0.3) {
      // Zoomed out - larger grid
      return { gap: 60, size: 5 };
    } else if (zoom < 0.5) {
      // Moderately zoomed out
      return { gap: 40, size: 3};
    } else if (zoom < 0.8) {
      // Slightly zoomed out
      return { gap: 30, size: 2 };
    } else if (zoom < 1.5) {
      // Normal zoom range
      return { gap: 20, size: 2 };
    } else {
      // Zoomed in - finer grid
      return { gap: 15, size: 1 };
    }
  }, [zoom]);

  return (
    <Background
      variant={BackgroundVariant.Dots}
      gap={gap}
      size={size}
      color="var(--color-grid)"
    />
  );
}
