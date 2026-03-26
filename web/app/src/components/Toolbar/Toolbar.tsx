import type { PlacementType } from '../../contexts/PlacementContext.js';
import styles from './Toolbar.module.css';

interface ToolbarProps {
  isPlacementMode: boolean;
  placementType: PlacementType | null;
  onEnterPlacementMode: (type: PlacementType) => void;
  onExitPlacementMode: () => void;
}

export function Toolbar({ isPlacementMode, placementType, onEnterPlacementMode, onExitPlacementMode }: ToolbarProps) {
  const handleSectionClick = () => {
    if (isPlacementMode && placementType === 'section') {
      onExitPlacementMode();
    } else {
      onEnterPlacementMode('section');
    }
  };

  const handleStickyClick = () => {
    if (isPlacementMode && placementType === 'sticky') {
      onExitPlacementMode();
    } else {
      onEnterPlacementMode('sticky');
    }
  };

  const handleNoteClick = () => {
    if (isPlacementMode && placementType === 'note') {
      onExitPlacementMode();
    } else {
      onEnterPlacementMode('note');
    }
  };

  const isSectionActive = isPlacementMode && placementType === 'section';
  const isStickyActive = isPlacementMode && placementType === 'sticky';
  const isNoteActive = isPlacementMode && placementType === 'note';

  return (
    <div className={styles.toolbar}>
      {/* Add Section button */}
      <button
        className={`${styles['toolbar-button']} ${styles.secondary} ${isSectionActive ? styles.active : ''}`}
        onClick={handleSectionClick}
        title="Add Section (S)"
      >
        <svg 
          width="20" 
          height="20" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="4 2" />
        </svg>
      </button>

      {/* Add Sticky button */}
      <button
        className={`${styles['toolbar-button']} ${styles.secondary} ${isStickyActive ? styles.active : ''}`}
        onClick={handleStickyClick}
        title="Add Sticky (T)"
      >
        <svg 
          width="20" 
          height="20" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M8 8h8M8 12h6" />
        </svg>
      </button>

      {/* Add Note button (primary) */}
      <button
        className={`${styles['toolbar-button']} ${isNoteActive ? styles.active : ''}`}
        onClick={handleNoteClick}
        title={isNoteActive ? 'Cancel placement' : 'Add Note'}
      >
        <svg 
          width="24" 
          height="24" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
          style={{ 
            transform: isNoteActive ? 'rotate(45deg)' : 'rotate(0deg)',
            transition: 'transform var(--transition-normal)'
          }}
        >
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </button>
    </div>
  );
}
