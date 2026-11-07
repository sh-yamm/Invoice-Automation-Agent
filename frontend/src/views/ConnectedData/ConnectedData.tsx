import { useEffect, useState } from "react";
import { getData } from "../../api/client";
import { inr } from "../../lib/format";

const SETS = [
  { key: "po_ledger", label: "Order balances", file: "purchase_orders.csv and the approval ledger" },
  { key: "vendors", label: "Vendor master", file: "vendors.csv" },
  { key: "purchase_orders", label: "Purchase orders", file: "purchase_orders.csv" },
  { key: "goods_receipts", label: "Goods receipts", file: "goods_receipts.csv" },
  { key: "contracts", label: "Contracts", file: "contracts.csv" },
  { key: "chart_of_accounts", label: "Chart of accounts", file: "chart_of_accounts.csv" },
];
const MONEY = new Set(["value", "invoiced", "remaining", "rate", "amount_per_period"]);
const HIDE = new Set(["address", "email", "phone"]);

function Ledger({ rows }: { rows: Record<string, any>[] }) {
  return (
    <table className="q">
      <thead><tr><th>PO</th><th>Vendor</th><th>Type</th><th className="amt">Value</th><th className="amt">Invoiced</th><th className="amt">Remaining</th><th>Billed so far</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.po_number}>
            <td className="mono">{r.po_number}</td><td>{r.vendor}</td><td>{r.po_type}</td>
            <td className="amt num">{inr(r.value)}</td><td className="amt num">{inr(r.invoiced)}</td><td className="amt num">{inr(r.remaining)}</td>
            <td style={{ whiteSpace: "nowrap" }}>
              <div className="minibar" style={{ display: "inline-flex", verticalAlign: "middle" }} role="img" aria-label={`${Math.round(r.used_pct)}% used`}>
                <b style={{ width: `${Math.min(100, r.used_pct)}%`, background: r.used_pct >= 100 ? "var(--rej)" : "var(--accent)" }} />
              </div>
              <span className="pct">{Math.round(r.used_pct)}%</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Generic({ rows }: { rows: Record<string, any>[] }) {
  const cols = Object.keys(rows[0] ?? {}).filter((c) => !HIDE.has(c));
  return (
    <table className="q">
      <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>{cols.map((c) => <td key={c} className={MONEY.has(c) ? "amt num" : undefined}>{MONEY.has(c) ? inr(r[c]) : String(r[c] ?? "")}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ConnectedData() {
  const [set, setSet] = useState("po_ledger");
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setRows([]);
    getData(set).then(setRows).catch((e) => setError(e.message));
  }, [set]);
  const meta = SETS.find((s) => s.key === set)!;
  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Company records</h1>
          <p className="sub">The agent checks invoices against these existing records and never edits them. The only thing that changes is the order ledger, and only when an invoice is approved.</p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="tablebox">
        <div className="tabs" role="tablist">
          {SETS.map((s) => <button key={s.key} role="tab" aria-selected={set === s.key} onClick={() => setSet(s.key)}>{s.label}</button>)}
        </div>
        <div className="panel-h"><h2>{meta.label}</h2><span className="source">Read from <span className="mono">{meta.file}</span></span></div>
        <div className="scroll">{set === "po_ledger" ? <Ledger rows={rows} /> : <Generic rows={rows} />}</div>
      </div>
    </section>
  );
}
