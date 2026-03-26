/**
 * Platform detection utilities for responsive/mobile behavior
 */

/**
 * Detects if the current device supports touch input.
 * Returns true for phones, tablets, and touch-enabled laptops.
 */
export function isTouchDevice(): boolean {
  if (typeof window === 'undefined') return false;
  return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
}

/**
 * Detects if the current viewport is mobile-sized (< 768px).
 * This is based on viewport width, not device type.
 */
export function isMobileViewport(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(max-width: 768px)').matches;
}

/**
 * Detects if the current viewport is tablet-sized (768px - 1024px).
 */
export function isTabletViewport(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(min-width: 768px) and (max-width: 1024px)').matches;
}

/**
 * Detects if the user prefers reduced motion.
 * Useful for disabling animations for accessibility.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}
