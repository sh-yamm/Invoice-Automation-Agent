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
  { href: "#queue", label: "Work queue", match: (h: string) => h === "" || h === "queue" },
  { href: "#rules", label: "Rulebook", match: (h: string) => h === "rules" },
  { href: "#data", label: "Connected data", match: (h: string) => h === "data" },
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
        <div className="wrap">
          <a className="brand" href="#queue" style={{ color: "inherit", textDecoration: "none" }}>
            <div className="brand-mark">Z</div>
            <div>
              Zentra AP Desk<small>Invoice agent · India</small>
            </div>
          </a>
          <nav className="views" aria-label="Views">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} aria-current={n.match(hash) ? "page" : undefined}>{n.label}</a>
            ))}
          </nav>
        </div>
      </header>
      <main className="wrap">{view}</main>
    </>
  );
}
