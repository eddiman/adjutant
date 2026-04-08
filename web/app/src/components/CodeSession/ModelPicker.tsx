import type { CliBackendInfo } from '../../hooks/useCodeSession';
import { Modal } from '../ui';

interface ModelPickerProps {
  open: boolean;
  backendInfo: CliBackendInfo;
  currentModel: string;
  onSelect: (model: string) => void;
  onClose: () => void;
}

export function ModelPicker({ open, backendInfo, currentModel, onSelect, onClose }: ModelPickerProps) {
  if (!open) return null;

  const tiers = [
    { label: 'cheap', id: backendInfo.models.cheap },
    { label: 'medium', id: backendInfo.models.medium },
    { label: 'expensive', id: backendInfo.models.expensive },
  ];

  return (
    <Modal open={open} onClose={onClose} title="Select Model" width="20rem">
      {tiers.map(tier => (
        <button
          key={tier.id}
          onClick={() => { onSelect(tier.id); onClose(); }}
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            width: '100%', padding: '0.625rem 1rem', background: currentModel === tier.id ? 'var(--color-primary-bg)' : 'none',
            border: 'none', borderBottom: '1px solid var(--color-border)', cursor: 'pointer',
            color: 'var(--color-text)', textAlign: 'left', fontFamily: 'inherit', fontSize: '0.8125rem',
          }}
        >
          <span style={{ fontWeight: 500 }}>{tier.label}</span>
          <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', fontFamily: "'SF Mono', monospace" }}>
            {tier.id}
          </span>
        </button>
      ))}
    </Modal>
  );
}
