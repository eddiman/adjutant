import type { SlashCommand } from '../../hooks/useSlashCommands';
import styles from './SlashCommandPalette.module.css';

interface SlashCommandPaletteProps {
  commands: SlashCommand[];
  selectedIndex: number;
  onSelect: (command: SlashCommand) => void;
}

export function SlashCommandPalette({ commands, selectedIndex, onSelect }: SlashCommandPaletteProps) {
  if (commands.length === 0) return null;

  return (
    <div className={styles.palette}>
      {commands.map((cmd, i) => (
        <button
          key={cmd.name}
          className={`${styles.item} ${i === selectedIndex ? styles.itemSelected : ''}`}
          onClick={() => onSelect(cmd)}
        >
          <span className={styles.name}>{cmd.name}</span>
          <span className={styles.description}>{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}
