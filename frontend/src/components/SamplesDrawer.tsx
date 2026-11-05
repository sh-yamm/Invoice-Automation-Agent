import { useEffect, useRef, useState } from "react";
import { getSamples } from "../api/client";
import type { Sample } from "../api/types";

interface Props {
  onClose: () => void;
  onPick: (sampleId: string) => void;
  onUpload: (file: File) => void;
}

export default function SamplesDrawer({ onClose, onPick, onUpload }: Props) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [over, setOver] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    getSamples().then(setSamples).catch(() => setSamples([]));
    closeRef.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" aria-label="Process an invoice">
        <div className="view-head" style={{ marginBottom: 0 }}>
          <div>
            <h2>Process an invoice</h2>
            <p className="sub">Drop a PDF to run it live, or pick a prepared case.</p>
          </div>
          <button ref={closeRef} className="btn small" onClick={onClose} aria-label="Close">✕</button>
        </div>
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
          <br />or click to choose a file. Text and scanned PDFs both work.
          <input type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
        </label>
        <div className="eyebrow">Demo samples</div>
        <div className="samples">
          {samples.map((s) => (
            <button key={s.id} className="sample" onClick={() => onPick(s.id)}>
              <span>
                <span className="t">{s.title}</span>
                <span className="b">{s.blurb}</span>
              </span>
              <span className="mono muted">{s.id}</span>
            </button>
          ))}
        </div>
      </aside>
    </>
  );
}
