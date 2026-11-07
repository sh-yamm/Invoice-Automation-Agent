import { useEffect, useState } from "react";
import { getAop, listCases, putAop, sendAction } from "../../api/client";

type Aop = Record<string, any>;

interface Rule {
  path: string;
  label: string;
  help: string;
  unit: string;
}

const SECTIONS: { title: string; rules: Rule[] }[] = [
  {
    title: "What the agent may approve alone",
    rules: [
      { path: "authority.auto_approve_limit_inr", label: "Auto-approve limit", help: "Above this the agent still checks everything, then asks the finance controller to sign off.", unit: "₹" },
      { path: "authority.po_less_auto_limit_inr", label: "PO-less auto limit", help: "PO-less invoices above this need the budget owner's sign-off.", unit: "₹" },
      { path: "authority.split_window_days", label: "Split-invoice window", help: "Invoices from one vendor inside this window are added up for the limit.", unit: "days" },
    ],
  },
  {
    title: "Tolerances",
    rules: [
      { path: "tolerance.price.over_pct", label: "Price tolerance (%)", help: "How far a billed rate may be above the PO rate.", unit: "%" },
      { path: "tolerance.price.over_abs_inr", label: "Price tolerance (₹ cap)", help: "…and the most extra money that tolerance may add on one line.", unit: "₹" },
      { path: "tolerance.qty_over_ordered_pct", label: "Quantity over ordered", help: "Billing for more than was ordered.", unit: "%" },
      { path: "tolerance.qty_over_received_pct", label: "Quantity over received", help: "Billing for more than was delivered and accepted.", unit: "%" },
      { path: "tolerance.po_balance_over_pct", label: "PO balance overrun", help: "Billing beyond the PO value.", unit: "%" },
      { path: "tolerance.contract_amount_pct", label: "Contract amount variance", help: "Recurring invoice vs the contract schedule.", unit: "%" },
    ],
  },
  {
    title: "Duplicates",
    rules: [
      { path: "duplicates.window_days", label: "Look-back window", help: "How far back to compare invoices from the same vendor.", unit: "days" },
      { path: "duplicates.min_similarity_pct", label: "Same-lines threshold", help: "Line similarity at which an invoice counts as a likely resend.", unit: "%" },
    ],
  },
  {
    title: "Confidence",
    rules: [
      { path: "confidence.min_field", label: "Minimum field confidence", help: "Below this the agent asks a person to confirm the field (0–1).", unit: "" },
      { path: "confidence.po_inference_min", label: "Minimum to infer a PO", help: "When no PO number is printed (0–1).", unit: "" },
      { path: "confidence.classification_min", label: "Minimum to classify", help: "Below this the transaction type goes to a person (0–1).", unit: "" },
      { path: "confidence.gl_coding_min", label: "Minimum for GL coding", help: "PO-less GL account choice (0–1).", unit: "" },
    ],
  },
];

const get = (o: Aop, path: string) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);

export default function Rulebook() {
  const [aop, setAop] = useState<Aop | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [why, setWhy] = useState("");
  const [msg, setMsg] = useState<{ tone: "error" | "ok"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [rechecking, setRechecking] = useState(false);

  const load = (a: Aop) => {
    setAop(a);
    setValues(Object.fromEntries(SECTIONS.flatMap((s) => s.rules).map((r) => [r.path, String(get(a, r.path))])));
  };
  useEffect(() => {
    getAop().then(load).catch((e) => setMsg({ tone: "error", text: e.message }));
  }, []);

  if (!aop) return <p className="muted">{msg?.text ?? "Loading the rulebook…"}</p>;
  const changed = Object.entries(values).filter(([p, v]) => Number(v) !== Number(get(aop, p)));

  async function save() {
    if (!changed.length) return setMsg({ tone: "error", text: "Nothing has changed." });
    if (!why.trim()) return setMsg({ tone: "error", text: "Say why you are changing the rulebook; it is kept with the version." });
    setSaving(true);
    try {
      const saved = await putAop(Object.fromEntries(changed.map(([p, v]) => [p, Number(v)])), "AP lead", why.trim());
      load(saved);
      setWhy("");
      setMsg({ tone: "ok", text: `Saved as version ${saved.version}. The next run follows it.` });
    } catch (e) {
      setMsg({ tone: "error", text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  }

  async function recheckHeld() {
    setRechecking(true);
    const held = (await listCases({ outcome: 2, status: "waiting" })).filter((c) => !c.is_seed);
    for (const c of held) {
      await sendAction(c.case_id, { action: "recheck", actor: "AP lead", action_key: `recheck-${c.case_id}-${aop?.version}` }).catch(() => undefined);
    }
    setRechecking(false);
    setMsg({ tone: "ok", text: held.length ? `Re-checked ${held.length} held ${held.length === 1 ? "invoice" : "invoices"} under version ${aop?.version}. Open the invoice list to see the new outcomes.` : "No demo invoices are on hold, so there was nothing to re-check." });
  }

  return (
    <section>
      <div className="page-head">
        <div>
          <h1>Rulebook</h1>
          <p className="sub">The agent reads these rules on every invoice. Change a number, give a reason and save: the next invoice follows the new rule. No code involved.</p>
          <div className="version">
            <span>Version {aop.version}</span>
            {aop.last_edit?.editor && <span>Last changed by {aop.last_edit.editor}{aop.last_edit.reason ? `: “${aop.last_edit.reason}”` : ""}</span>}
          </div>
        </div>
        <button className="btn" disabled={rechecking} onClick={recheckHeld}>{rechecking ? "Re-checking…" : "Re-check held invoices"}</button>
      </div>
      {msg && <p className={msg.tone === "error" ? "error" : "notice"}>{msg.text}</p>}
      <div className="rules">
        {SECTIONS.map((s) => (
          <div key={s.title} className="rule-sec">
            <h2>{s.title}</h2>
            {s.rules.map((r) => {
              const dirty = Number(values[r.path]) !== Number(get(aop, r.path));
              return (
                <div key={r.path} className={`rule${dirty ? " changed" : ""}`}>
                  <div><label className="rt" htmlFor={r.path}>{r.label}</label><p>{r.help}</p></div>
                  <div className="rule-in">
                    {r.unit === "₹" && <span className="unit" style={{ minWidth: 0 }}>₹</span>}
                    <input id={r.path} type="number" step="any" value={values[r.path] ?? ""}
                           onChange={(e) => setValues({ ...values, [r.path]: e.target.value })} />
                    <span className="unit">{r.unit === "₹" ? "" : r.unit}</span>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
        <div className="rule-sec locked-sec">
          <h2>Always stop and ask a person</h2>
          <p>These checks can never be approved by the agent or loosened here. A person must verify them.</p>
          {(aop.locked as string[]).map((code) => {
            const r = (aop.reasons as any[]).find((x) => x.code === code);
            return (
              <div key={code} className="rule" data-testid={`locked-${code}`}>
                <div><div className="rt mono">{code}</div><p>{r?.owner ? `Goes to ${r.owner}. ` : ""}{r?.next}</p></div>
                <span className="lock" aria-label="Locked">🔒 Locked</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className={`save-bar${changed.length ? "" : " idle"}`}>
        <div className="wrap">
          <span className="state">{changed.length ? `${changed.length} unsaved ${changed.length === 1 ? "change" : "changes"}` : "No unsaved changes"}</span>
          <label htmlFor="why">Why are you changing it?</label>
          <input id="why" type="text" value={why} onChange={(e) => setWhy(e.target.value)} placeholder="For example: steel prices rose this quarter" />
          <button className="btn primary" disabled={saving} onClick={save}>Save rulebook</button>
        </div>
      </div>
    </section>
  );
}
