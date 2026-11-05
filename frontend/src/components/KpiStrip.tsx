import type { Kpis } from "../api/types";
import { lakh } from "../lib/format";

function Sparkline({ points }: { points: (number | null)[] }) {
  const w = 150, h = 34;
  const vals = points.map((p) => p ?? 0);
  const lo = Math.min(...vals, 40), hi = Math.max(...vals, 80);
  const x = (i: number) => 4 + (i * (w - 8)) / Math.max(1, vals.length - 1);
  const y = (v: number) => h - 4 - ((v - lo) / Math.max(1, hi - lo)) * (h - 8);
  const line = vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const last = vals.length - 1;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Touchless rate, last 7 days">
      <polygon points={`${x(0)},${h - 4} ${line} ${x(last)},${h - 4}`} fill="var(--accent-wash)" />
      <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      <circle cx={x(last)} cy={y(vals[last] ?? 0)} r="3.5" fill="var(--accent)" stroke="var(--sheet)" strokeWidth="2" />
    </svg>
  );
}

export default function KpiStrip({ kpis }: { kpis: Kpis }) {
  return (
    <div className="kpis">
      <div className="kpi">
        <div className="l">Invoices processed</div>
        <div className="v">{kpis.processed}</div>
        <div className="d">{lakh(kpis.total_inr)} in total</div>
      </div>
      <div className="kpi">
        <div className="l">Touchless rate</div>
        <div className="v">{Math.round(kpis.touchless_pct)}%</div>
        <Sparkline points={kpis.touchless_series.map((s) => s.touchless_pct)} />
      </div>
      <div className="kpi">
        <div className="l">Exceptions caught</div>
        <div className="v">{kpis.exceptions}</div>
        <div className="d">each with a reason and an owner</div>
      </div>
      <div className="kpi">
        <div className="l">Protected from fraud and duplicates</div>
        <div className="v">{lakh(kpis.protected_inr)}</div>
        <div className="d">{kpis.protected_cases} invoice(s) stopped</div>
      </div>
      <div className="kpi">
        <div className="l">Average handling time</div>
        <div className="v">{kpis.avg_handling_seconds !== null ? `${Math.round(kpis.avg_handling_seconds)} s` : "—"}</div>
        <div className="d">manual AP benchmark is about 9 days</div>
      </div>
    </div>
  );
}

export function OutcomeBar({ outcomes }: { outcomes: Kpis["outcomes"] }) {
  const parts = [
    { key: "approved", label: "Approved", color: "var(--ok)" },
    { key: "needs_signoff", label: "Needs sign-off", color: "var(--sign)" },
    { key: "on_hold", label: "On hold", color: "var(--hold)" },
    { key: "rejected", label: "Rejected", color: "var(--rej)" },
  ] as const;
  const total = parts.reduce((s, p) => s + outcomes[p.key], 0);
  return (
    <div className="flow">
      <h2>Where {total} invoices ended up</h2>
      <div className="flowbar" role="img" aria-label={parts.map((p) => `${outcomes[p.key]} ${p.label}`).join(", ")}>
        {parts.map((p) => (outcomes[p.key] ? <div key={p.key} style={{ flex: outcomes[p.key], background: p.color }} title={`${p.label}: ${outcomes[p.key]}`} /> : null))}
      </div>
      <div className="flowlegend">
        {parts.map((p) => (
          <span key={p.key}>
            <i className="sw" style={{ background: p.color }} />
            {p.label} <b>{outcomes[p.key]}</b>
          </span>
        ))}
      </div>
    </div>
  );
}
