import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';

export type PlacementType = 'note' | 'section' | 'sticky';

interface PlacementContextValue {
  // State
  isPlacementMode: boolean;
  placementType: PlacementType | null;
  isCreating: boolean;
  
  // Actions
  enterPlacementMode: (type: PlacementType) => void;
  togglePlacementMode: () => void;
  exitPlacementMode: () => void;
  setIsCreating: (creating: boolean) => void;
}

const PlacementContext = createContext<PlacementContextValue | null>(null);

interface PlacementProviderProps {
  children: ReactNode;
}

export function PlacementProvider({ children }: PlacementProviderProps) {
  const [isPlacementMode, setIsPlacementMode] = useState(false);
  const [placementType, setPlacementType] = useState<PlacementType | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const enterPlacementMode = useCallback((type: PlacementType) => {
    setPlacementType(type);
    setIsPlacementMode(true);
  }, []);

  const togglePlacementMode = useCallback(() => {
    if (isPlacementMode) {
      setIsPlacementMode(false);
      setPlacementType(null);
    } else {
      setPlacementType('note');
      setIsPlacementMode(true);
    }
  }, [isPlacementMode]);

  const exitPlacementMode = useCallback(() => {
    setIsPlacementMode(false);
    setPlacementType(null);
  }, []);

  // Escape key to exit placement mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isPlacementMode) {
        setIsPlacementMode(false);
        setPlacementType(null);
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isPlacementMode]);

  const value: PlacementContextValue = {
    isPlacementMode,
    placementType,
    isCreating,
    enterPlacementMode,
    togglePlacementMode,
    exitPlacementMode,
    setIsCreating,
  };

  return (
    <PlacementContext.Provider value={value}>
      {children}
    </PlacementContext.Provider>
  );
}

export function usePlacement() {
  const context = useContext(PlacementContext);
  if (!context) {
    throw new Error('usePlacement must be used within a PlacementProvider');
  }
  return context;
}
