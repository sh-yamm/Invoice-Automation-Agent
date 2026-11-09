import { useEffect, useState } from "react";
import ConnectedData from "./views/ConnectedData/ConnectedData";
import LiveCase from "./views/LiveCase/LiveCase";
import Rulebook from "./views/Rulebook/Rulebook";
import WorkQueue from "./views/WorkQueue/WorkQueue";

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash.slice(1));
  useEffect(() => {
    const on = () => {
      setHash(window.location.hash.slice(1));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

const NAV = [
  { href: "#queue", icon: "receipt_long", label: "Invoices", match: (h: string) => h === "" || h === "queue" || h.startsWith("case-") },
  { href: "#rules", icon: "gavel", label: "Rulebook", match: (h: string) => h === "rules" },
  { href: "#data", icon: "inventory_2", label: "Company records", match: (h: string) => h === "data" },
];

export default function App() {
  const hash = useHash();
  let view = <WorkQueue />;
  if (hash.startsWith("case-")) view = <LiveCase key={hash} caseId={hash.slice(5)} />;
  else if (hash === "rules") view = <Rulebook />;
  else if (hash === "data") view = <ConnectedData />;

  return (
    <>
      <header className="top">
        <nav className="views" aria-label="Views">
          {NAV.map((n) => (
            <a key={n.href} href={n.href} aria-current={n.match(hash) ? "page" : undefined}>
              <span className="ms" aria-hidden="true">{n.icon}</span>{n.label}
            </a>
          ))}
        </nav>
        <a className="brand" href="#queue">
          <span className="brand-mark" aria-hidden="true">Z</span>Zamp Invoice Agent
        </a>
      </header>
      <main className="wrap">
        {view}
        <footer className="foot">Zamp Invoice Agent · accounts payable for Zentra Retail · every decision traced to a rule</footer>
      </main>
    </>
  );
}
