import { useCallback, useEffect, useMemo, useState } from "react";
import { createCase, getKpis, listCases, resetDemo } from "../../api/client";
import type { CaseSummary, Kpis, Outcome, Pace, TxnType } from "../../api/types";
import { StatusChip, TypeBadge } from "../../components/Chips";
import KpiStrip, { OutcomeBar } from "../../components/KpiStrip";
import SamplesDrawer from "../../components/SamplesDrawer";
import { ago, inr, TXN } from "../../lib/format";

const TABS: { key: "all" | Outcome; label: string }[] = [
  { key: "all", label: "All" },
  { key: 2, label: "Needs attention" },
  { key: 1, label: "Awaiting sign-off" },
  { key: 0, label: "Approved" },
  { key: 3, label: "Rejected" },
];

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

  async function start(input: { sampleId?: string; file?: File }) {
    setError(null);
    try {
      const { case_id } = await createCase({ ...input, pace });
      setDrawer(false);
      window.location.hash = `case-${case_id}`;
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section>
      <div className="view-head">
        <div>
          <div className="eyebrow">Accounts payable · Zentra Retail Pvt Ltd</div>
          <h1>Work queue</h1>
          <p className="sub">The agent handles routine invoices on its own. You only see the ones that need a person.</p>
        </div>
        <div className="toolbar">
          <label className="muted" htmlFor="pace">Pace</label>
          <select id="pace" value={pace} onChange={(e) => setPace(e.target.value as Pace)}>
            <option value="normal">Normal</option>
            <option value="presenter">Presenter</option>
            <option value="fast">Fast</option>
          </select>
          <button className="btn" onClick={() => resetDemo().then(load)}>Reset demo</button>
          <button className="btn primary" onClick={() => setDrawer(true)}>Demo samples · Upload</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {kpis && <KpiStrip kpis={kpis} />}
      {kpis && <OutcomeBar outcomes={kpis.outcomes} />}

      <div className="tablebox">
        <div className="tabs" role="tablist">
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
                <th>Vendor · invoice</th>
                <th>Type</th>
                <th className="amt">Amount</th>
                <th>Status</th>
                <th>Why</th>
                <th>Owner</th>
                <th>Age</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.case_id} tabIndex={0} onClick={() => (window.location.hash = `case-${c.case_id}`)}
                    onKeyDown={(e) => e.key === "Enter" && (window.location.hash = `case-${c.case_id}`)}>
                  <td>
                    <div className="vend">{c.vendor_name ?? c.filename ?? "Reading…"}</div>
                    <div className="sub2 mono">{c.invoice_no ?? c.case_id}</div>
                  </td>
                  <td><TypeBadge type={c.txn_type} /></td>
                  <td className="amt num">{inr(c.grand_total)}</td>
                  <td><StatusChip outcome={c.outcome} status={c.status} /></td>
                  <td className="reason">{c.why ?? ""}</td>
                  <td>{c.owner ?? ""}</td>
                  <td className="num muted">{ago(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="empty">No invoices here.</div>}
        </div>
      </div>
      {drawer && (
        <SamplesDrawer onClose={() => setDrawer(false)} onPick={(id) => start({ sampleId: id })} onUpload={(f) => start({ file: f })} />
      )}
    </section>
  );
}
