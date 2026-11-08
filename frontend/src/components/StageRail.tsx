import type { CaseEvent, Finding, TxnType } from "../api/types";

const MATCH: Record<TxnType, [string, string]> = {
  standard_po: ["Match", "PO · receipt"],
  recurring: ["Contract", "period · balance"],
  po_less: ["Code & route", "policy · GL"],
};

export const RAIL = [
  { key: "receive", label: "Receive", sub: "file · pages", nodes: ["ingest", "render", "parse"], stages: ["ingest"] },
  { key: "read", label: "Read", sub: "fields · tamper", nodes: ["reconcile", "extract", "ground"], stages: ["reconcile", "read"] },
  { key: "classify", label: "Classify", sub: "document · type", nodes: ["classify_document", "classify_transaction"], stages: ["classify"] },
  { key: "validate", label: "Validate", sub: "GST rules", nodes: ["validate"], stages: ["validate"] },
  { key: "match", label: "Match", sub: "", nodes: ["standard_po", "recurring", "po_less"], stages: ["match"] },
  { key: "controls", label: "Controls", sub: "fraud · duplicates", nodes: ["controls"], stages: ["controls"] },
  { key: "decide", label: "Decide", sub: "rules + agent", nodes: ["completeness_guard", "decide", "human_gate", "finalise"], stages: ["decide", "human", "finalise"] },
];

export function railKeyForStage(stage: string): string {
  return RAIL.find((r) => r.stages.includes(stage))?.key ?? "decide";
}

interface Props {
  events: CaseEvent[];
  findings: Finding[];
  txnType: TxnType | null;
  running: boolean;
}

export default function StageRail({ events, findings, txnType, running }: Props) {
  const started = new Set(events.filter((e) => e.type === "node_started").map((e) => String(e.payload.node)));
  const finished = new Set(events.filter((e) => e.type === "node_finished").map((e) => String(e.payload.node)));
  return (
    <ol className="rail" aria-label="Pipeline stages">
      {RAIL.map((r, i) => {
        const fs = findings.filter((f) => railKeyForStage(f.stage) === r.key);
        const hasFail = fs.some((f) => f.status === "fail");
        const reject = fs.some((f) => f.status === "fail" && f.outcome === 3);
        const touched = r.nodes.some((n) => started.has(n)) || fs.length > 0;
        const active = running && r.nodes.some((n) => started.has(n) && !finished.has(n));
        const state = active ? "active" : reject ? "fail" : hasFail ? "warn" : touched ? "done" : "";
        const [label, sub] = r.key === "match" && txnType ? MATCH[txnType] : [r.label, r.sub];
        return (
          <li key={r.key} className={`stage ${state}`}>
            <span className="dot" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
            <span className="nm">{label}{state && <span className="sr">{` (${state === "done" ? "done" : state === "warn" ? "needs a look" : state === "fail" ? "stopped" : "running"})`}</span>}</span>
            <span className="t">{sub}</span>
          </li>
        );
      })}
    </ol>
  );
}
