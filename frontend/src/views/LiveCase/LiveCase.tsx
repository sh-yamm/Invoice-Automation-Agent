import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCase, sendAction, streamEvents } from "../../api/client";
import type { ActionBody, CaseDetail, CaseEvent, Finding } from "../../api/types";
import { TypeBadge } from "../../components/Chips";
import PdfEvidence from "../../components/PdfEvidence";
import StageRail from "../../components/StageRail";
import { inr, TXN } from "../../lib/format";
import { ActionBar, AgentNote, ConfirmField, DecisionCard, DuplicateCompare, FindingLog, LedgerBar, LineTable } from "./Panels";

const key = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`);

export default function LiveCase({ caseId }: { caseId: string }) {
  const [c, setC] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [hover, setHover] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const close = useRef<() => void>(() => undefined);

  const refresh = useCallback(() => getCase(caseId).then(setC).catch((e) => setError(e.message)), [caseId]);

  const connect = useCallback(() => {
    close.current();
    setStreaming(true);
    close.current = streamEvents(
      caseId,
      (e) => {
        setEvents((prev) => (prev.some((x) => x.seq === e.seq && x.type === e.type) ? prev : [...prev, e]));
        if (e.type === "decision" || e.type === "finalised") refresh();
      },
      () => {
        setStreaming(false);
        refresh();
      },
    );
  }, [caseId, refresh]);

  useEffect(() => {
    setEvents([]);
    refresh();
    connect();
    return () => close.current();
  }, [caseId, refresh, connect]);

  const eventFindings = useMemo(
    () => events.filter((e) => e.type === "finding").map((e) => e.payload as unknown as Finding),
    [events],
  );
  const current: Finding[] = !streaming && c?.findings.length ? c.findings : eventFindings.length ? eventFindings : c?.findings ?? [];

  async function act(body: Omit<ActionBody, "action_key">) {
    setBusy(true);
    setError(null);
    try {
      const updated = await sendAction(caseId, { ...body, action_key: key() });
      setC(updated);
      connect();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!c) return <p className="muted">{error ?? "Opening the case…"}</p>;
  const running = c.status === "running";
  const replay = c.llm_calls.some((l) => l.model.endsWith("(cached)"));
  const checks = current.length;
  const problems = current.filter((f) => f.status === "fail").length;

  return (
    <section>
      <a href="#queue" className="back">← All invoices</a>
      <div className="case-head">
        <div>
          <h1>{c.vendor_name ?? c.filename ?? "Reading the invoice…"}</h1>
          <div className="meta">
            <span className="mono">{c.invoice_no ?? c.case_id}</span>
            <span className="amount num">{inr(c.grand_total)}</span>
            <TypeBadge type={c.txn_type} />
            <span className={`tag ${replay ? "" : "live"}`} title={replay ? "This demo invoice replays model answers recorded earlier, so it runs the same way every time." : "Every model call is made live."}>
              {replay ? "Recorded model replies" : "Live models"}
            </span>
            {c.sample_id && <span className="label">Demo invoice {c.sample_id}, case {c.case_id}</span>}
          </div>
          {c.txn_type && (
            <p className="classified">
              Classified as {TXN[c.txn_type]} ({Math.round((c.txn_confidence ?? 0) * 100)}% sure): {c.txn_why}
            </p>
          )}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <StageRail events={events} findings={current} txnType={c.txn_type} running={running || streaming} />
      <div className="desk">
        <PdfEvidence
          pages={c.pages}
          findings={current}
          hover={hover}
          scanned={current.some((f) => f.check === "render" && f.title.includes("scanned"))}
          stamp={c.outcome !== null && !running ? { outcome: c.outcome, code: c.primary_code } : null}
        />
        <div className="stack">
          {c.outcome === null && (
            <div className="panel pad">
              <h2>Working on it</h2>
              <p className="muted">The agent is reading and checking this invoice. Each check appears below the moment it runs, and the decision lands here.</p>
            </div>
          )}
          <DecisionCard c={c} />
          <ConfirmField key={`${c.status}-${c.primary_code}`} c={c} findings={current} busy={busy} onAct={act} />
          <ActionBar c={c} busy={busy} onAct={act} />
          <LedgerBar findings={current} />
          <DuplicateCompare findings={current} />
          <AgentNote c={c} />
          <div className="panel">
            <div className="panel-h">
              <h2>Every check, in order</h2>
              <span className="label">
                {running || streaming ? "running…" : `${checks} checks, ${problems === 0 ? "no problems" : problems === 1 ? "1 problem" : `${problems} problems`}`}
              </span>
            </div>
            <FindingLog events={events} fallback={c.findings} onHover={setHover} />
          </div>
          <LineTable c={c} findings={current} />
        </div>
      </div>
    </section>
  );
}
