import { useEffect, useMemo, useState } from "react";
import { getData } from "../../api/client";
import { day } from "../../components/PaperTrail";
import { inr } from "../../lib/format";

type Row = Record<string, any>;
const TABS = [
  { key: "orders", label: "Orders and deliveries", help: "Every purchase order Zentra has issued, what has arrived against it, and how much has been billed." },
  { key: "vendors", label: "Vendors", help: "Who Zentra buys from. The agent checks each invoice's GSTIN and bank account against this list." },
  { key: "contracts", label: "Contracts", help: "Recurring services billed every period. The agent checks the period and the amount." },
  { key: "gl", label: "Expense accounts", help: "Where spend without a purchase order (power, internet, rent) is booked." },
] as const;
type Tab = (typeof TABS)[number]["key"];

function Steps() {
  return (
    <ol className="howbuy" aria-label="How buying works at Zentra">
      <li><b>Zentra issues a purchase order</b><span>What it wants, how many, at what price.</span></li>
      <li><b>The vendor delivers</b><span>The warehouse records a goods receipt for what arrived.</span></li>
      <li><b>The vendor sends an invoice</b><span>The agent matches it to the order and the receipt.</span></li>
      <li><b>Approved invoices are paid</b><span>The order's balance goes down by the amount billed.</span></li>
    </ol>
  );
}

function Orders({ pos, grns, ledger }: { pos: Row[]; grns: Row[]; ledger: Row[] }) {
  const orders = useMemo(() => {
    const byPo = new Map<string, Row[]>();
    for (const l of pos) byPo.set(l.po_number, [...(byPo.get(l.po_number) ?? []), l]);
    return ledger.map((b) => ({ b, lines: byPo.get(b.po_number) ?? [], receipts: grns.filter((g) => g.po_number === b.po_number) }));
  }, [pos, grns, ledger]);
  return (
    <div className="orders">
      {orders.map(({ b, lines, receipts }) => {
        const head = lines[0] ?? {};
        const used = Math.round(b.used_pct);
        return (
          <article key={b.po_number} className="order">
            <header>
              <div>
                <h3 className="mono">{b.po_number}</h3>
                <div className="label">{b.vendor}, issued {day(head.po_date)}</div>
              </div>
              <span className="tag">{b.po_type === "blanket" ? "Blanket order" : b.po_type === "services" ? "Services" : "Goods"}, {head.status ?? "open"}</span>
            </header>
            <table className="grid">
              <thead><tr><th>Ordered</th><th className="r">Quantity</th><th className="r">Rate</th><th>Delivered</th></tr></thead>
              <tbody>
                {lines.map((l) => {
                  const got = receipts.filter((g) => g.line_no === l.line_no);
                  const accepted = got.reduce((s, g) => s + Number(g.accepted_qty), 0);
                  return (
                    <tr key={l.line_no}>
                      <td>{l.description}</td>
                      <td className="r">{Number(l.qty).toLocaleString("en-IN")} {l.unit}</td>
                      <td className="r">{inr(l.rate)}</td>
                      <td>{b.po_type !== "goods" ? <span className="muted">no delivery needed</span>
                        : got.length ? <>{accepted.toLocaleString("en-IN")} {l.unit} <span className="muted">({got.map((g) => `${g.grn_number}, ${day(g.received_date)}`).join("; ")})</span></>
                        : <span className="cell-bad">not delivered yet</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <footer>
              <div className="minibar" role="img" aria-label={`${used}% used`}>
                <b style={{ width: `${Math.min(100, b.used_pct)}%`, background: b.used_pct >= 100 ? "var(--rej)" : "var(--accent)" }} />
              </div>
              <span>Billed <b>{inr(b.invoiced, 0)}</b> of <b>{inr(b.value)}</b>, {inr(b.remaining, 0)} left ({used}% used)</span>
            </footer>
          </article>
        );
      })}
    </div>
  );
}

function Vendors({ rows }: { rows: Row[] }) {
  return (
    <table className="q">
      <thead><tr><th>Vendor</th><th>GSTIN</th><th>Buys</th><th>Bank account on file</th><th>Pays in</th><th>E-invoice</th><th>Status</th></tr></thead>
      <tbody>
        {rows.map((v) => (
          <tr key={v.vendor_id}>
            <td><div className="vend">{v.name}</div><div className="sub2">{v.address}</div></td>
            <td className="mono">{v.gstin}</td>
            <td>{String(v.category).replace(/_/g, " ")}</td>
            <td>{v.bank_name} <span className="mono">····{String(v.bank_account).slice(-4)}</span></td>
            <td>{v.payment_terms_days} days</td>
            <td>{v.einvoice_required ? "Required" : "Not required"}</td>
            <td>{v.status === "active" ? <span className="chip approved"><i>✓</i>Approved</span> : <span className="chip reject"><i>✕</i>{v.status}</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Contracts({ rows, vendors }: { rows: Row[]; vendors: Row[] }) {
  return (
    <table className="q">
      <thead><tr><th>Contract</th><th>Vendor</th><th>What for</th><th className="amt">Per period</th><th>Runs</th><th>Order</th></tr></thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.contract_id}>
            <td className="mono">{c.contract_id}</td>
            <td>{vendors.find((v) => v.vendor_id === c.vendor_id)?.name ?? c.vendor_id}</td>
            <td>{c.description}</td>
            <td className="amt num">{inr(c.amount_per_period)} <span className="muted">{c.billing_cycle}</span></td>
            <td>{day(c.start_date)} to {day(c.end_date)}</td>
            <td className="mono">{c.po_number}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Accounts({ rows }: { rows: Row[] }) {
  return (
    <table className="q">
      <thead><tr><th>Account</th><th>Name</th><th>Used for</th><th>Approved by</th></tr></thead>
      <tbody>
        {rows.map((a) => (
          <tr key={a.gl_code}><td className="mono">{a.gl_code}</td><td className="vend">{a.name}</td><td>{a.description}</td><td>{a.budget_owner}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

export default function ConnectedData() {
  const [tab, setTab] = useState<Tab>("orders");
  const [data, setData] = useState<Record<string, Row[]>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    for (const name of ["po_ledger", "purchase_orders", "goods_receipts", "vendors", "contracts", "chart_of_accounts"]) {
      getData(name).then((rows) => setData((d) => ({ ...d, [name]: rows }))).catch((e) => setError(e.message));
    }
  }, []);
  const meta = TABS.find((t) => t.key === tab)!;
  const d = (k: string) => data[k] ?? [];
  return (
    <section>
      <div className="page-head">
        <div>
          <p className="eyebrow">What every invoice is checked against</p>
          <h1>Company records</h1>
          <p className="sub">Zentra's own records that every invoice is checked against. The agent only reads them; the one thing it updates is how much of each order has been billed, and only when an invoice is approved.</p>
        </div>
      </div>
      <Steps />
      {error && <p className="error">{error}</p>}
      <div className="tablebox">
        <div className="tabs" role="tablist" aria-label="Records">
          {TABS.map((t) => <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}>{t.label}</button>)}
        </div>
        <p className="tab-help">{meta.help}</p>
        {tab === "orders" && <Orders pos={d("purchase_orders")} grns={d("goods_receipts")} ledger={d("po_ledger")} />}
        {tab === "vendors" && <div className="scroll"><Vendors rows={d("vendors")} /></div>}
        {tab === "contracts" && <div className="scroll"><Contracts rows={d("contracts")} vendors={d("vendors")} /></div>}
        {tab === "gl" && <div className="scroll"><Accounts rows={d("chart_of_accounts")} /></div>}
      </div>
    </section>
  );
}
