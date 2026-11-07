import { useCallback, useEffect, useMemo, useState } from "react";
import { createCase, getKpis, listCases, resetDemo } from "../../api/client";
import type { CaseSummary, Kpis, Outcome, Pace, TxnType } from "../../api/types";
import { StatusChip, TypeBadge } from "../../components/Chips";
import KpiStrip from "../../components/KpiStrip";
import SamplesDrawer from "../../components/SamplesDrawer";
import { ago, inr, TXN } from "../../lib/format";

const TABS: { key: "all" | Outcome; label: string }[] = [
  { key: "all", label: "All" },
  { key: 2, label: "On hold" },
  { key: 1, label: "Awaiting sign-off" },
  { key: 0, label: "Approved" },
  { key: 3, label: "Rejected" },
];

const open = (id: string) => (window.location.hash = `case-${id}`);
const needsPerson = (c: CaseSummary) => (c.outcome === 1 || c.outcome === 2) && c.status !== "done";

export default function WorkQueue() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [tab, setTab] = useState<"all" | Outcome>("all");
  const [type, setType] = useState<"all" | TxnType>("all");
  const [drawer, setDrawer] = useState(false);
  const [pace, setPace] = useState<Pace>("normal");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listCases().then(setCases).catch((e) => setError(e.message));
    getKpis().then(setKpis).catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const byType = useMemo(() => cases.filter((c) => type === "all" || c.txn_type === type), [cases, type]);
  const rows = useMemo(() => byType.filter((c) => tab === "all" || c.outcome === tab), [byType, tab]);
  const count = (k: "all" | Outcome) => (k === "all" ? byType.length : byType.filter((c) => c.outcome === k).length);
  const needs = useMemo(() => cases.filter(needsPerson), [cases]);
  const running = cases.filter((c) => c.status === "running").length;

  async function start(input: { sampleId?: string; file?: File }) {
    setError(null);
    try {
      const { case_id } = await createCase({ ...input, pace });
      setDrawer(false);
      open(case_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const headline = needs.length === 0 ? "Nothing needs you right now" : needs.length === 1 ? "1 invoice needs you" : `${needs.length} invoices need you`;
  const auto = kpis ? `The agent finished ${kpis.touchless} of ${kpis.processed} invoices without anyone.` : "";

  return (
    <section>
      <div className="greet">
        <div>
          <h1><span className="count-word">{headline}</span></h1>
          <p className="sub">
            {auto} Each exception below says what is wrong, who should look at it, and what to do next.
            {running > 0 && ` ${running} still being read.`}
          </p>
        </div>
        <button className="btn primary" onClick={() => setDrawer(true)}>Process an invoice</button>
      </div>
      {error && <p className="error">{error}</p>}

      <section className="needs" aria-label="Needs a person">
        <div className="needs-h">
          <h2>Waiting for a person</h2>
          <span className="label">oldest first</span>
        </div>
        {needs.length === 0 ? (
          <div className="allclear">Every processed invoice was approved, rejected or already handled. New exceptions appear here.</div>
        ) : (
          <ul>
            {[...needs].reverse().map((c) => (
              <li key={c.case_id}>
                <a className={`need ${c.outcome === 1 ? "signoff" : "hold"}`} href={`#case-${c.case_id}`}>
                  <span className="edge" aria-hidden="true" />
                  <span className="who">
                    {c.vendor_name ?? c.filename}
                    <small><span className="mono">{c.invoice_no ?? c.case_id}</span>, {ago(c.created_at)} ago</small>
                  </span>
                  <span className="what"><b>{c.owner}:</b> {c.why}</span>
                  <span className="go">
                    <span className="amt num">{inr(c.grand_total, 0)}</span>
                    <span className="btn small">Review</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      {kpis && <KpiStrip kpis={kpis} />}

      <div className="section-h">
        <h2>All invoices</h2>
        <span className="label">Click a row to see every check the agent ran</span>
      </div>
      <div className="tablebox">
        <div className="tabs" role="tablist" aria-label="Outcome">
          {TABS.map((t) => (
            <button key={String(t.key)} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
              <span className="count">{count(t.key)}</span>
            </button>
          ))}
        </div>
        <div className="filters" aria-label="Transaction type">
          <button aria-pressed={type === "all"} onClick={() => setType("all")}>All types</button>
          {(Object.keys(TXN) as TxnType[]).map((k) => (
            <button key={k} aria-pressed={type === k} onClick={() => setType(k)}>
              {TXN[k]} <span className="count">{cases.filter((c) => c.txn_type === k).length}</span>
            </button>
          ))}
        </div>
        <div className="scroll">
          <table className="q">
            <thead>
              <tr>
                <th>Vendor and invoice</th>
                <th>Outcome</th>
                <th className="amt">Amount</th>
                <th>Reason</th>
                <th>Owner</th>
                <th>Type</th>
                <th>Received</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.case_id} className="click" tabIndex={0} onClick={() => open(c.case_id)}
                    onKeyDown={(e) => e.key === "Enter" && open(c.case_id)}>
                  <td>
                    <div className="vend">{c.vendor_name ?? c.filename ?? "Reading…"}</div>
                    <div className="sub2 mono">{c.invoice_no ?? c.case_id}</div>
                  </td>
                  <td><StatusChip outcome={c.outcome} status={c.status} /></td>
                  <td className="amt num">{inr(c.grand_total)}</td>
                  <td className="reason">{c.why ?? ""}</td>
                  <td>{c.owner ?? ""}</td>
                  <td><TypeBadge type={c.txn_type} /></td>
                  <td className="num muted">{ago(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="empty">No invoices with this outcome and type.</div>}
        </div>
      </div>
      {drawer && (
        <SamplesDrawer onClose={() => setDrawer(false)} onPick={(id) => start({ sampleId: id })} onUpload={(f) => start({ file: f })}
                       pace={pace} onPace={setPace} onReset={() => resetDemo().then(load)} />
      )}
    </section>
  );
}
