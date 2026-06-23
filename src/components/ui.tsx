import type { ReactNode } from "react";
import type { CountItem, SourceType } from "../types";

export function Stat({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  icon?: string;
}) {
  return (
    <div className="stat">
      <div className="label">
        {icon && <span>{icon}</span>}
        {label}
      </div>
      <div className="value">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function BarList({ items, max = 6 }: { items: CountItem[]; max?: number }) {
  const top = items.slice(0, max);
  const peak = Math.max(1, ...top.map((i) => i.count));
  return (
    <div className="barlist">
      {top.map((it) => (
        <div className="barrow" key={it.label}>
          <span className="bl" title={it.label}>
            {it.label}
          </span>
          <span className="bartrack">
            <span className="barfill" style={{ width: `${(it.count / peak) * 100}%` }} />
          </span>
          <span className="bv">{it.count}</span>
        </div>
      ))}
    </div>
  );
}

const SOURCE_STYLE: Record<SourceType, string> = {
  "Website Knowledge": "brand",
  "CRM Demo Dataset": "green",
  "ERP Demo Dataset": "amber",
  "Ticketing Demo Dataset": "red",
  "Approved Web Source": "",
};

export function SourceBadge({ source }: { source: SourceType }) {
  return <span className={`badge dot ${SOURCE_STYLE[source]}`}>{source}</span>;
}
