import type { Kpis } from "../api/types";
import { lakh } from "../lib/format";

function Sparkline({ points }: { points: (number | null)[] }) {
  const w = 84, h = 26;
  const vals = points.map((p) => p ?? 0);
  const lo = Math.min(...vals, 40), hi = Math.max(...vals, 80);
  const x = (i: number) => 3 + (i * (w - 6)) / Math.max(1, vals.length - 1);
  const y = (v: number) => h - 3 - ((v - lo) / Math.max(1, hi - lo)) * (h - 6);
  const line = vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const last = vals.length - 1;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Touchless rate, last 7 days" style={{ marginBottom: 4 }}>
      <polyline points={line} fill="none" stroke="var(--ink-2)" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={x(last)} cy={y(vals[last] ?? 0)} r="3" fill="var(--accent)" />
    </svg>
  );
}

const PARTS = [
  { key: "approved", label: "Approved", color: "var(--ok)" },
  { key: "needs_signoff", label: "Needs sign-off", color: "var(--sign)" },
  { key: "on_hold", label: "On hold", color: "var(--hold)" },
  { key: "rejected", label: "Rejected", color: "var(--rej)" },
] as const;

/** One quiet band of numbers that answer "is the agent doing its job?", with where every invoice ended up. */
export default function KpiStrip({ kpis }: { kpis: Kpis }) {
  const o = kpis.outcomes;
  return (
    <section className="band" aria-label="How the agent is doing">
      <div>
        <div className="v">{kpis.processed}</div>
        <div className="l">Invoices processed</div>
        <div className="d">{lakh(kpis.total_inr)} in total</div>
      </div>
      <div>
        <div className="v">{Math.round(kpis.touchless_pct)}%<Sparkline points={kpis.touchless_series.map((s) => s.touchless_pct)} /></div>
        <div className="l">Done with no person</div>
        <div className="d">last 7 days</div>
      </div>
      <div>
        <div className="v">{kpis.exceptions}</div>
        <div className="l">Exceptions caught</div>
        <div className="d">each with a reason and an owner</div>
      </div>
      <div>
        <div className="v">{lakh(kpis.protected_inr)}</div>
        <div className="l">Stopped as fraud or duplicate</div>
        <div className="d">{kpis.protected_cases === 1 ? "1 invoice" : `${kpis.protected_cases} invoices`}</div>
      </div>
      <div>
        <div className="v">{kpis.avg_handling_seconds !== null ? `${Math.round(kpis.avg_handling_seconds)} s` : "—"}</div>
        <div className="l">Average handling time</div>
        <div className="d">a manual AP team takes about 9 days</div>
      </div>
      <div className="split">
        <div className="outbar" role="img" aria-label={PARTS.map((p) => `${o[p.key]} ${p.label}`).join(", ")}>
          {PARTS.map((p) => (o[p.key] ? <div key={p.key} style={{ flex: o[p.key], background: p.color }} title={`${p.label}: ${o[p.key]}`} /> : null))}
        </div>
        <div className="outlegend">
          {PARTS.map((p) => (
            <span key={p.key}><i className="sw" style={{ background: p.color }} />{p.label} <b>{o[p.key]}</b></span>
          ))}
        </div>
      </div>
    </section>
  );
}
