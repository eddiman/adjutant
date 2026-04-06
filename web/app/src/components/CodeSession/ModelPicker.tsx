import type { CliBackendInfo } from '../../hooks/useCodeSession';

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
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--cs-card)', border: '1px solid var(--cs-border)',
          borderRadius: '0.5rem', width: '20rem', overflow: 'hidden',
        }}
      >
        <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid var(--cs-border)' }}>
          <h3 style={{ margin: 0, fontSize: '0.875rem', color: 'var(--cs-text)' }}>Select Model</h3>
        </div>
        {tiers.map(tier => (
          <button
            key={tier.id}
            onClick={() => { onSelect(tier.id); onClose(); }}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              width: '100%', padding: '0.625rem 1rem', background: currentModel === tier.id ? 'rgba(124,92,191,0.1)' : 'none',
              border: 'none', borderBottom: '1px solid var(--cs-border)', cursor: 'pointer',
              color: 'var(--cs-text)', textAlign: 'left', fontFamily: 'inherit', fontSize: '0.8125rem',
            }}
          >
            <span style={{ fontWeight: 500 }}>{tier.label}</span>
            <span style={{ color: 'var(--cs-text-muted)', fontSize: '0.75rem', fontFamily: "'SF Mono', monospace" }}>
              {tier.id}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
