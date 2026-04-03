

interface ConfidenceBadgeProps {
  confidence: number;
}

export default function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  let label: string;
  let colorVar: string;

  if (confidence >= 85) {
    label = 'AUTO';
    colorVar = 'var(--status-auto)';
  } else if (confidence >= 60) {
    label = 'REVIEW';
    colorVar = 'var(--status-review)';
  } else {
    label = 'FLAG';
    colorVar = 'var(--status-flag)';
  }

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      padding: '2px 6px',
      borderRadius: '2px',
      fontSize: '11px',
      fontWeight: '600',
      letterSpacing: '0.05em',
      backgroundColor: `color-mix(in srgb, ${colorVar} 15%, transparent)`,
      color: colorVar,
      border: `1px solid color-mix(in srgb, ${colorVar} 30%, transparent)`
    }}>
      {label} {confidence}%
    </span>
  );
}
