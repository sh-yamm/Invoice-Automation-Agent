import type { Outcome, Status, TxnType } from "../api/types";
import { OUTCOME, TXN } from "../lib/format";

export function StatusChip({ outcome, status }: { outcome: Outcome | null; status?: Status }) {
  if (outcome === null || status === "running") {
    return (
      <span className="chip running">
        <i aria-hidden="true">…</i>Processing
      </span>
    );
  }
  const o = OUTCOME[outcome];
  return (
    <span className={`chip ${o.tone}`}>
      <i aria-hidden="true">{o.icon}</i>
      {o.label}
      {status === "waiting_vendor" ? " · asked vendor" : ""}
    </span>
  );
}

export function TypeBadge({ type }: { type: TxnType | null }) {
  if (!type) return <span className="badge">Unclassified</span>;
  return <span className={`badge ${type}`}>{TXN[type]}</span>;
}
