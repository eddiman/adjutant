import type { CanvasTool } from '../../types';
import styles from './ToolSwitcher.module.css';

interface ToolSwitcherProps {
  activeTool: CanvasTool;
  onToolChange: (tool: CanvasTool) => void;
  sidebarOpen: boolean;
}

export function ToolSwitcher({ activeTool, onToolChange, sidebarOpen }: ToolSwitcherProps) {
  return (
    <div className={`${styles['tool-switcher']} ${sidebarOpen ? styles['sidebar-open'] : ''}`}>
      <button
        className={`${styles['tool-switcher-btn']} ${activeTool === 'pan' ? styles.active : ''}`}
        onClick={() => onToolChange('pan')}
        aria-label="Pan tool"
        title="Pan (drag to pan, pinch to zoom)"
      >
        {/* Hand/Pan icon */}
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 11V6a2 2 0 00-2-2 2 2 0 00-2 2v0M14 10V4a2 2 0 00-2-2 2 2 0 00-2 2v6" />
          <path d="M10 10.5V6a2 2 0 00-2-2 2 2 0 00-2 2v8" />
          <path d="M18 8a2 2 0 012 2v7c0 3-3.5 5-6 5h-2.5a7 7 0 01-5.2-2.3L4 17.3a1.5 1.5 0 01-.3-2.1 1.5 1.5 0 012.1-.3L8 16" />
        </svg>
      </button>
      <button
        className={`${styles['tool-switcher-btn']} ${activeTool === 'select' ? styles.active : ''}`}
        onClick={() => onToolChange('select')}
        aria-label="Select tool"
        title="Select (tap to select, drag to move)"
      >
        {/* Cursor/Select icon */}
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z" />
          <path d="M13 13l6 6" />
        </svg>
      </button>
    </div>
  );
}
