import type { Finding, Outcome } from "../api/types";
import { OUTCOME } from "../lib/format";

interface Props {
  pages: string[];
  findings: Finding[];
  hover: string | null;
  stamp: { outcome: Outcome; code: string | null } | null;
  scanned: boolean;
}

/** The invoice page images with a box over every place a check took its evidence from. */
export default function PdfEvidence({ pages, findings, hover, stamp, scanned }: Props) {
  const boxed = findings.flatMap((f) =>
    f.evidence.map((e, i) => ({ f, e, i })).filter(({ e }) => e.box && e.page),
  );
  return (
    <div className="sheet-wrap">
      <div className="sheet-label">
        <span><b>{scanned ? "Scanned copy" : "The invoice as received"}</b>{scanned ? ", read from the image" : ""}</span>
        <span>Point at a check to see where on the page it looked</span>
      </div>
      {pages.length === 0 && <div className="sheet-empty">Opening the PDF…</div>}
      {pages.map((src, idx) => (
        <div key={src} className="page">
          <img src={src} alt={`Invoice page ${idx + 1}`} />
          {boxed
            .filter(({ e }) => e.page === idx + 1)
            .map(({ f, e, i }) => {
              const [x0, y0, x1, y1] = e.box!;
              const tone = f.status === "fail" ? (f.outcome === 3 ? "reject" : "hold") : f.status === "warn" ? "warn" : "ok";
              return (
                <div
                  key={`${f.id}-${i}`}
                  data-testid={`box-${f.id}-${i}`}
                  className={`evbox ${tone}${hover === f.id ? " hl" : ""}`}
                  style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
                />
              );
            })}
          {idx === 0 && stamp && (
            <div className={`stamp ${OUTCOME[stamp.outcome].tone}`}>
              {OUTCOME[stamp.outcome].label.toUpperCase()}
              <small>{stamp.code}</small>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
