import { useState, useCallback, useMemo } from 'react';

export interface SlashCommand {
  name: string;
  description: string;
  action: string;
}

const COMMANDS: SlashCommand[] = [
  { name: '/help', description: 'Show available commands', action: 'help' },
  { name: '/new', description: 'Start a new session', action: 'new' },
  { name: '/sessions', description: 'View past sessions', action: 'sessions' },
  { name: '/browse', description: 'Change working directory', action: 'browse' },
  { name: '/model', description: 'Switch model', action: 'model' },
  { name: '/cost', description: 'Show cost summary', action: 'cost' },
];

export function useSlashCommands() {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filteredCommands = useCallback((prefix: string): SlashCommand[] => {
    if (!prefix.startsWith('/')) return [];
    const search = prefix.toLowerCase();
    return COMMANDS.filter(cmd => cmd.name.toLowerCase().startsWith(search));
  }, []);

  const moveUp = useCallback(() => {
    setSelectedIndex(prev => Math.max(0, prev - 1));
  }, []);

  const moveDown = useCallback((maxIndex: number) => {
    setSelectedIndex(prev => Math.min(maxIndex, prev + 1));
  }, []);

  const resetSelection = useCallback(() => {
    setSelectedIndex(0);
  }, []);

  return useMemo(() => ({
    commands: COMMANDS,
    filteredCommands,
    selectedIndex,
    moveUp,
    moveDown,
    resetSelection,
  }), [filteredCommands, selectedIndex, moveUp, moveDown, resetSelection]);
}
