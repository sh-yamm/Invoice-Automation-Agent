import { useEffect, useRef, useState } from "react";
import { getSamples } from "../api/client";
import type { Pace, Sample } from "../api/types";
import { OUTCOME } from "../lib/format";

interface Props {
  onClose: () => void;
  onPick: (sampleId: string) => void;
  onUpload: (file: File) => void;
  pace: Pace;
  onPace: (p: Pace) => void;
  onReset: () => void;
}

const PACES: { key: Pace; label: string }[] = [
  { key: "fast", label: "Fast" },
  { key: "normal", label: "Normal" },
  { key: "presenter", label: "Slow, for presenting" },
];

export default function SamplesDrawer({ onClose, onPick, onUpload, pace, onPace, onReset }: Props) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [over, setOver] = useState(false);
  const [reset, setReset] = useState<"idle" | "busy" | "done">("idle");
  const ref = useRef<HTMLDialogElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    getSamples().then(setSamples).catch(() => setSamples([]));
    const d = ref.current;
    if (!d) return;
    // Native modal: the browser keeps focus inside, closes on Esc (and outside click via closedby), and returns focus.
    if (typeof d.showModal === "function") d.showModal();
    else d.setAttribute("open", "");
    const closed = () => onCloseRef.current();
    d.addEventListener("close", closed);
    return () => d.removeEventListener("close", closed);
  }, []);

  const close = () => (typeof ref.current?.close === "function" ? ref.current.close() : onCloseRef.current());

  return (
    <dialog ref={ref} className="drawer" aria-labelledby="drawer-title" {...{ closedby: "any" }}>
        <div className="drawer-h">
          <div>
            <h2 id="drawer-title">Process an invoice</h2>
            <p className="sub">Upload a PDF to run it through the agent with live models, or pick one of the prepared invoices below.</p>
          </div>
          <button className="btn ghost small" onClick={close} aria-label="Close" autoFocus>✕</button>
        </div>
        <div className="drawer-body">
          <label
            className={`drop${over ? " over" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setOver(false);
              const f = e.dataTransfer.files[0];
              if (f) onUpload(f);
            }}
          >
            <strong>Drop an invoice PDF here</strong>
            <span>or click to choose a file. Digital and scanned PDFs both work.</span>
            <input type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
          </label>
          <div>
            <h3>Prepared invoices</h3>
            <p className="sub" style={{ margin: "2px 0 10px", fontSize: 13.5 }}>Each one tests a different situation. The dot shows the outcome it should reach.</p>
            <div className="samples">
              {samples.map((s) => (
                <button key={s.id} className="sample" onClick={() => onPick(s.id)}>
                  <i className={`dot2 ${OUTCOME[s.expected_outcome]?.tone ?? ""}`} aria-hidden="true" />
                  <span>
                    <span className="t">{s.title}</span>
                    <span className="b">{s.blurb}</span>
                    <span className="e">{s.id}, expected: {OUTCOME[s.expected_outcome]?.label.toLowerCase()}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="drawer-foot">
          <div className="row">
            <span className="label" id="pace-l">Run speed</span>
            <div className="seg" role="group" aria-labelledby="pace-l">
              {PACES.map((p) => (
                <button key={p.key} aria-pressed={pace === p.key} onClick={() => onPace(p.key)}>{p.label}</button>
              ))}
            </div>
          </div>
          <div className="row">
            <span className="label">{reset === "done" ? "Demo data restored to its starting point." : "Clear demo runs and restore the starting history."}</span>
            <button className="btn small" disabled={reset === "busy"} onClick={() => { setReset("busy"); Promise.resolve(onReset()).finally(() => setReset("done")); }}>
              {reset === "busy" ? "Resetting…" : "Reset demo data"}
            </button>
          </div>
        </div>
    </dialog>
  );
}
