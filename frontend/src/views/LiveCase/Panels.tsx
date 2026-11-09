import { useState } from "react";
import type { ActionBody, CaseDetail, CaseEvent, Finding } from "../../api/types";
import { railKeyForStage } from "../../components/StageRail";
import { inr, OUTCOME } from "../../lib/format";

const ICON = { pass: "✓", warn: "!", fail: "✕" } as const;
const STAGE_NAME: Record<string, string> = {
  receive: "Receiving the file", read: "Reading the invoice", classify: "Working out what it is", validate: "GST rules",
  match: "Matching to the order", controls: "Fraud and duplicate controls", decide: "Decision",
};

export function FindingLog({ events, fallback, onHover }: {
  events: CaseEvent[]; fallback: Finding[]; onHover: (id: string | null) => void;
}) {
  const items = events.length
    ? events.filter((e) => ["finding", "human_action", "decision"].includes(e.type))
    : fallback.map((f, i) => ({ type: "finding", seq: i, payload: f as unknown as Record<string, unknown> }));
  let lastStage = "";
  const out: JSX.Element[] = [];
  for (const e of items) {
    const stage = e.type === "finding" ? railKeyForStage((e.payload as unknown as Finding).stage) : "decide";
    if (stage !== lastStage) {
      out.push(<li key={`s${e.seq}-${stage}`} className="stage-h" aria-hidden="true">{STAGE_NAME[stage] ?? stage}</li>);
      lastStage = stage;
    }
    if (e.type === "human_action") {
      const p = e.payload as Record<string, string>;
      out.push(
        <li key={`h${e.seq}`} className="human">
          <span className="ic" aria-label="Person">◉</span>
          <div><div className="tt">{p.actor ?? "Person"}: {p.action?.replace(/_/g, " ")}</div>{p.note && <div className="dd">“{p.note}”</div>}</div>
        </li>,
      );
      continue;
    }
    if (e.type === "decision") {
      const p = e.payload as Record<string, string>;
      out.push(
        <li key={`d${e.seq}`} className="decision-line">
          <span className="ic" aria-hidden="true">⚖</span>
          <div><div className="tt">Decision recorded<span className="cd">{p.primary_code}</span></div><div className="dd">{p.next_step}</div></div>
        </li>,
      );
      continue;
    }
    const f = e.payload as unknown as Finding;
    out.push(
      <li key={f.id + e.seq} className={`${f.status} ${f.outcome === 3 ? "reject" : "hold"}`}
          onMouseOver={() => onHover(f.evidence.some((x) => x.box) ? f.id : null)}>
        <span className="ic" aria-label={f.status}>{ICON[f.status]}</span>
        <div>
          <div className="tt">{f.title}{f.status !== "pass" && f.code && <span className="cd">{f.code}</span>}</div>
          {f.detail && <div className="dd">{f.detail}</div>}
        </div>
      </li>,
    );
  }
  return <ul className="log" onMouseLeave={() => onHover(null)}>{out}</ul>;
}

export function DecisionCard({ c }: { c: CaseDetail }) {
  if (c.outcome === null) return null;
  const o = OUTCOME[c.outcome];
  const waiting = c.status === "waiting" || c.status === "waiting_vendor";
  return (
    <section className={`decision ${o.tone}`} aria-label="Decision">
      <div className="row-between">
        <div className="verdict">{o.label}{c.status === "waiting_vendor" ? ", asked the vendor" : ""}</div>
        <span className="code" title="Reason code from the rulebook">{c.primary_code}</span>
      </div>
      <div className="why">{c.why}</div>
      <dl className="facts">
        <dt>{waiting ? "Who should act" : "Handled by"}</dt><dd>{c.owner}</dd>
        <dt>Next step</dt><dd>{c.next_step}</dd>
      </dl>
      {c.also.length > 0 && (
        <div className="also"><span className="label">Also found</span><ul>{c.also.map((a) => <li key={a}>{a}</li>)}</ul></div>
      )}
    </section>
  );
}

export function AgentNote({ c }: { c: CaseDetail }) {
  const review = c.llm_calls.find((l) => l.node === "agent_review");
  if (!c.agent_note && !review) return null;
  return (
    <div className="panel pad agent">
      <h3>The agent's second look</h3>
      <p className="label">After the rules decide, the agent reviews the whole case. It may only make the outcome stricter, never approve.</p>
      <p>{c.agent_note}</p>
      {review?.reasoning && (
        <details>
          <summary>Show its full reasoning</summary>
          <pre className="reasoning">{review.reasoning}</pre>
        </details>
      )}
    </div>
  );
}

export function ActionBar({ c, busy, onAct }: { c: CaseDetail; busy: boolean; onAct: (b: Omit<ActionBody, "action_key">) => void }) {
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  if (!["waiting", "waiting_vendor"].includes(c.status) || c.outcome === null) return null;
  const actions: [ActionBody["action"], string, string][] =
    c.outcome === 1
      ? [["sign_off", "Sign off", "primary"], ["reject", "Reject", "danger"], ["recheck", "Re-check", ""]]
      : [["approve_anyway", "Approve anyway", "primary"], ["reject", "Reject", "danger"], ["ask_vendor", "Ask vendor", ""], ["recheck", "Re-check", ""]];
  function go(action: ActionBody["action"]) {
    if (action === "approve_anyway" && c.locked_codes.length && !note.trim()) {
      setMsg(`A verification note is required to approve over ${c.locked_codes.join(", ")}.`);
      return;
    }
    setMsg(null);
    onAct({ action, note: note.trim() || undefined, actor: "AP reviewer" });
  }
  return (
    <div className="panel pad actions-panel">
      <h3>Your decision</h3>
      <label htmlFor="note" className="label">Note {c.locked_codes.length ? "(required to approve, because a locked rule failed)" : "(optional, saved in the audit trail)"}</label>
      <textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
                placeholder={c.locked_codes.length ? "How was this verified? For example: called the vendor on the number on file" : "For example: new rate agreed with the vendor by email"} />
      {msg && <p className="error">{msg}</p>}
      <div className="actions">
        {actions.map(([a, label, tone]) => (
          <button key={a} className={`btn ${tone}`} disabled={busy} onClick={() => go(a)}>{label}</button>
        ))}
      </div>
    </div>
  );
}

function toInputDate(v: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : v;
}

export function ConfirmField({ c, findings, busy, onAct }: {
  c: CaseDetail; findings: Finding[]; busy: boolean; onAct: (b: Omit<ActionBody, "action_key">) => void;
}) {
  const low = findings.find((f) => f.code === "LOW_CONFIDENCE_FIELD" && f.status === "fail");
  const values = (low?.data.values ?? {}) as Record<string, string>;
  const field = Object.keys(values)[0];
  const [value, setValue] = useState(field ? toInputDate(values[field]) : "");
  if (!low || !field || c.status !== "waiting") return null;
  const label = field.replace(/_/g, " ");
  return (
    <div className="panel pad">
      <h3>Confirm one field</h3>
      <p className="sub">{low.detail}</p>
      <div className="field-confirm">
        <label htmlFor={`cf-${field}`}>{label}</label>
        <input id={`cf-${field}`} type="text" value={value} onChange={(e) => setValue(e.target.value)} />
        <button className="btn primary small" disabled={busy} onClick={() => onAct({ action: "confirm_field", field, value, actor: "AP reviewer" })}>
          Confirm and continue
        </button>
      </div>
    </div>
  );
}

const num = (s: unknown) => Number(String(s ?? "0").replace(/[₹,\s]/g, "")) || 0;

export function LedgerBar({ findings }: { findings: Finding[] }) {
  const f = findings.find((x) => x.code === "AMOUNT_EXCEEDS_PO_BALANCE" || x.code === "PO_FULLY_INVOICED");
  if (!f) return null;
  const value = num(f.data.po_value), billed = num(f.data.invoiced), now = num(f.data.this_amount);
  const max = Math.max(value, billed + now) || 1;
  const fits = Math.max(0, Math.min(now, value - billed));
  const over = Math.max(0, billed + now - value);
  return (
    <div className="panel pad">
      <h3>{String(f.data.po)}: how much of the order is left</h3>
      <div className="ledger" role="img" aria-label={`Ordered ${inr(value)}, billed ${inr(billed)}, this invoice ${inr(now)}`}>
        {billed > 0 && <div style={{ flex: billed / max, background: "var(--ink-2)" }} />}
        {fits > 0 && <div style={{ flex: fits / max, background: "var(--hold)" }} />}
        {over > 0 && <div className="over" style={{ flex: Math.max(over / max, 0.04) }} />}
      </div>
      <div className="ledger-key">
        <span><i className="sw" style={{ background: "var(--ink-2)" }} />Already billed <b>{inr(billed, 0)}</b></span>
        <span><i className="sw" style={{ background: "var(--hold)" }} />This invoice <b>{inr(now, 0)}</b></span>
        {over > 0 && <span className="bad"><i className="sw over" />Over the order by <b>{inr(over, 0)}</b></span>}
      </div>
      <p className="label">Order value {inr(value, 0)}, of which {inr(Math.max(0, value - billed), 0)} was left before this invoice.</p>
    </div>
  );
}

export function DuplicateCompare({ findings }: { findings: Finding[] }) {
  const f = findings.find((x) => ["DUPLICATE_PROBABLE", "DUPLICATE_EXACT", "PERIOD_ALREADY_BILLED"].includes(x.code ?? "") && x.status === "fail");
  if (!f || !f.data.other_case) return null;
  return (
    <div className="panel pad">
      <h3>This looks like an invoice we already have</h3>
      <p>
        <a href={`#case-${String(f.data.other_case)}`}>{String(f.data.other_no)}</a>
        {f.data.reasons ? `: ${String(f.data.reasons)}` : ""}
      </p>
    </div>
  );
}

export function LineTable({ c, findings }: { c: CaseDetail; findings: Finding[] }) {
  const lines = c.invoice?.lines ?? [];
  if (!lines.length) return null;
  const flag = (desc: string) =>
    findings.find((f) => f.status === "fail" && String(f.data.item ?? "") === desc);
  return (
    <div className="panel">
      <div className="panel-h"><h2>Invoice lines</h2><span className="muted">{c.txn_type === "standard_po" ? "checked against the PO and receipt" : ""}</span></div>
      <div className="scroll">
        <table className="grid">
          <thead><tr><th>Item</th><th>HSN/SAC</th><th className="r">Qty</th><th className="r">Rate</th><th className="r">Taxable</th><th>Check</th></tr></thead>
          <tbody>
            {lines.map((l) => {
              const bad = flag(l.description);
              return (
                <tr key={l.description}>
                  <td>{l.description}</td><td className="mono">{l.hsn_sac}</td>
                  <td className="r mono">{Number(l.qty).toLocaleString("en-IN")} {l.unit}</td>
                  <td className="r mono">{inr(l.rate)}</td><td className="r mono">{inr(l.taxable)}</td>
                  <td className={bad ? "cell-bad" : "cell-ok"}>{bad ? bad.title : "✓"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
