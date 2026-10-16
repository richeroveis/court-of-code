import { useId } from "react";

interface GaugeProps {
  value: number;
  max?: number;
  unitLabel?: string;
  caption?: string;
  accent?: string;
  accent2?: string;
  size?: number;
}

// Crisp custom SVG ring gauge with a gradient stroke, used for the split-award bps and
// the simulator's live consensus score.
export default function Gauge({
  value,
  max = 10000,
  unitLabel = "bps",
  caption,
  accent = "#22d3ee",
  accent2 = "#e2be60",
  size = 168,
}: GaugeProps) {
  const gid = useId().replace(/:/g, "");
  const stroke = 14;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value / max));
  const offset = c * (1 - pct);
  return (
    <div className="gauge">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${Math.round(pct * 100)} percent`}>
        <defs>
          <linearGradient id={`g-${gid}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={accent} />
            <stop offset="100%" stopColor={accent2} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#g-${gid})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="gauge-arc"
        />
        <text x="50%" y="46%" textAnchor="middle" className="gauge-num">
          {Math.round(pct * 100)}%
        </text>
        <text x="50%" y="60%" textAnchor="middle" className="gauge-sub">
          {value} {unitLabel}
        </text>
      </svg>
      {caption && <div className="gauge-cap">{caption}</div>}
    </div>
  );
}
