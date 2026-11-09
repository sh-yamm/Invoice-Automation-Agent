import type { Line, Trail, TrailStep } from "../api/types";
import { inr } from "../lib/format";

const LANES: { key: string; label: string; sub: string; kinds: TrailStep["kind"][] }[] = [
  { key: "buyer", label: "Zentra Retail", sub: "the buyer", kinds: ["contract", "po", "grn"] },
  { key: "vendor", label: "Vendor", sub: "the seller", kinds: ["earlier", "invoice"] },
  { key: "agent", label: "Agent and people", sub: "accounts payable", kinds: ["check", "decision", "person"] },
];
const ICON: Record<TrailStep["kind"], string> = {
  contract: "✍", po: "▤", grn: "⬇", earlier: "↺", invoice: "₹", check: "✓", decision: "⚖", person: "◉",
};

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

/** The chain of events behind one invoice, one column per event, in three lanes by who acted. */
export default function PaperTrail({ trail }: { trail: Trail }) {
  const steps = trail.steps;
  const cols = `minmax(96px, 0.5fr) repeat(${steps.length}, minmax(136px, 1fr))`;
  return (
    <section className="trail" aria-label="Paper trail">
      <div className="trail-h">
        <div>
          <h2>How this invoice got here</h2>
          <p className="label">Every document in the chain, in date order: what Zentra ordered, what the vendor delivered and billed, and what happened next.</p>
        </div>
      </div>
      <div className="scroll">
        <ol className="trail-grid" style={{ gridTemplateColumns: cols }}>
          <li className="lane-label axis" aria-hidden="true" />
          {steps.map((s, i) => (
            <li key={`a${i}`} className={`axis-dot k-${s.kind}`} style={{ gridColumn: i + 2 }} aria-hidden="true">
              <span className="n">{i + 1}</span><span className="d">{day(s.date)}</span>
            </li>
          ))}
          {LANES.map((lane, r) => (
            <li key={lane.key} className="lane-row" style={{ display: "contents" }}>
              <div className="lane-label" style={{ gridRow: r + 2 }}><b>{lane.label}</b><span>{lane.sub}</span></div>
              {steps.map((s, i) =>
                lane.kinds.includes(s.kind) ? (
                  <div key={i} className={`step k-${s.kind}`} style={{ gridColumn: i + 2, gridRow: r + 2 }}>
                    <span className="ic" aria-hidden="true">{ICON[s.kind]}</span>
                    <div>
                      <div className="st">{s.case_id ? <a href={`#case-${s.case_id}`}>{s.title}</a> : s.title}</div>
                      <div className="sd">{s.detail}</div>
                      <div className="sw2">{day(s.date)}{s.who && lane.key !== "buyer" ? `, ${s.who}` : ""}</div>
                    </div>
                  </div>
                ) : (
                  <div key={i} className="cell-empty" style={{ gridColumn: i + 2, gridRow: r + 2 }} aria-hidden="true" />
                ),
              )}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const n = (s: string | null | undefined) => Number(String(s ?? "").replace(/[₹,\s]/g, "")) || 0;
const qty = (v: string | number | null | undefined, unit?: string | null) =>
  v === null || v === undefined || v === "" ? "—" : `${Number(v).toLocaleString("en-IN")}${unit ? ` ${unit}` : ""}`;

function pair(trail: Trail, lines: Line[]) {
  const po = trail.po!.lines;
  return po.map((pl, i) => {
    const inv = lines.find((l) => l.hsn_sac && l.hsn_sac === pl.hsn_sac) ?? (po.length === lines.length ? lines[i] : undefined);
    return { pl, inv };
  });
}

/** Ordered vs received vs billed, line by line: the 3-way match a clerk would do by hand. */
export function MatchTable({ trail }: { trail: Trail }) {
  if (!trail.po || !trail.invoice) return null;
  const services = trail.po.po_type !== "goods";
  const rows = pair(trail, trail.invoice.lines);
  return (
    <div className="panel">
      <div className="panel-h">
        <h2>Ordered, received, billed</h2>
        <span className="label">{services ? "Services: no delivery receipt, so a 2-way match" : "Goods: a 3-way match"}</span>
      </div>
      <div className="scroll">
        <table className="grid match">
          <thead>
            <tr>
              <th>Item</th>
              <th className="r">Ordered on {trail.po.po_number}</th>
              {!services && <th className="r">Received</th>}
              <th className="r">Billed earlier</th>
              <th className="r">This invoice</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ pl, inv }) => {
              const rateUp = inv && n(inv.rate) > n(pl.rate);
              const overReceived = inv && pl.received_qty !== null && n(inv.qty) > n(pl.received_qty);
              const overOrdered = inv && n(inv.qty) + n(pl.billed_before_qty) > n(pl.qty);
              return (
                <tr key={pl.line_no}>
                  <td>{pl.description}<div className="sub2 mono">{pl.item_code}, HSN/SAC {pl.hsn_sac}</div></td>
                  <td className="r">{qty(pl.qty, pl.unit)}<div className="sub2">at {inr(pl.rate)}</div></td>
                  {!services && (
                    <td className="r">{pl.received_qty === null ? <span className="cell-bad">Nothing yet</span> : qty(pl.received_qty, pl.unit)}
                      <div className="sub2">{pl.received_date ? day(pl.received_date) : "no receipt"}</div></td>
                  )}
                  <td className="r">{n(pl.billed_before_amount) ? qty(pl.billed_before_qty, pl.unit) : "—"}
                    <div className="sub2">{n(pl.billed_before_amount) ? inr(pl.billed_before_amount, 0) : "nothing billed"}</div></td>
                  <td className="r">
                    {inv ? (
                      <>
                        <span className={overReceived || overOrdered ? "cell-bad" : undefined}>{qty(inv.qty, inv.unit)}</span>
                        <div className={`sub2${rateUp ? " cell-bad" : ""}`}>at {inr(inv.rate)}{rateUp ? `, ${(((n(inv.rate) - n(pl.rate)) / n(pl.rate)) * 100).toFixed(1)}% above the PO` : ""}</div>
                      </>
                    ) : <span className="muted">not on this invoice</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
