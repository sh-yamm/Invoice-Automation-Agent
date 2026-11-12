"""Page styles: the reference theme's measured values (Thumbstop Engine), applied on top of Streamlit."""
import streamlit as st

CSS = """
<style>
:root {
  --paper:#fffaf4; --sheet:#fffdf9; --card:#ffffff; --ink:#2e1f17; --body:#3d2c22; --ink-2:#5a4436; --muted:#6b5444; --faint:#8a7262;
  --rule:#d6bb9f; --rule-2:#e5cfb8; --wash:#fae6d4; --pill:#f2e0cd; --track:#efd6c2;
  --accent:#b5502c; --accent-deep:#8f3c1f; --accent-line:#e7b99c;
  --ok:#2f7a4b; --ok-wash:#e4f1e5; --sign:#6a46b8; --sign-wash:#efe8f8; --hold:#9a6a00; --hold-wash:#fbefc8; --rej:#b3213f; --rej-wash:#fae0e4;
  --hero: radial-gradient(120% 140% at 0% 0%, #fbe3d0 0%, #fff5ea 45%, #fffaf4 100%);
  --display: "Fraunces", Georgia, serif; --mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}
[data-testid="stMainBlockContainer"] { max-width: 1180px; padding: 72px 80px 120px; }
@media (max-width: 1000px) { [data-testid="stMainBlockContainer"] { padding: 24px 24px 80px; } }
[data-testid="stHeader"] { background: var(--paper); }
#MainMenu, footer, [data-testid="stStatusWidget"] { visibility: hidden; }
a { color: var(--accent-deep); }
.mono { font-family: var(--mono); font-size: .88em; }
.muted { color: var(--faint); }
.eyebrow { margin: 0; font-size: 12.8px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--accent-deep); }
.cap { font-size: 11.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
.h2 { font-family: var(--display); font-size: 24px; font-weight: 600; color: var(--ink); margin: 8px 0 12px; line-height: 1.2; }
.h3 { font-family: var(--display); font-size: 20px; font-weight: 600; color: var(--ink); margin: 0; }
.note { color: var(--muted); font-size: 13px; }

/* hero */
.hero { background: var(--hero); border: 1px solid var(--rule); border-radius: 16px; padding: 22px 26px 19px; margin: 0 0 18px; }
.hero h1 { font-family: var(--display); font-size: 37.6px; font-weight: 700; line-height: 1.1; letter-spacing: -.01em; margin: 6px 0 8px; padding: 0; color: var(--ink); }
.hero p { color: var(--body); font-size: 16px; line-height: 1.6; max-width: 64ch; margin: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.chip { font-size: 12.5px; color: var(--ink-2); background: var(--card); border: 1px solid var(--rule); border-radius: 999px; padding: 2px 10px; }
.chip b { color: var(--ink); font-weight: 600; }
.pill { display: inline-block; font-size: 12.2px; color: var(--ink-2); background: var(--pill); border-radius: 999px; padding: 2px 9px; white-space: nowrap; }
.pill.live { background: var(--ok-wash); color: var(--ok); }

/* KPI cards */
.kpis { display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 9.6px; margin: 4px 0 10px; }
.kpi { background: var(--card); border: 1px solid var(--rule); border-radius: 12px; padding: 11.2px 13.6px; }
.kpi .v { font-family: var(--display); font-size: 28px; font-weight: 700; line-height: 1.1; color: var(--ink); }
.kpi .l { font-size: 12.8px; color: var(--muted); margin-top: 2.4px; }
.kpi .d { font-size: 11.8px; color: var(--faint); }
@media (max-width: 900px) { .kpis { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.outbox { background: var(--card); border: 1px solid var(--rule); border-radius: 12px; padding: 12px 14px; margin-bottom: 18px; }
.outbar { display: flex; height: 8px; border-radius: 999px; overflow: hidden; gap: 2px; background: var(--track); }
.legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 8px; font-size: 12.8px; color: var(--muted); }
.legend i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 6px; }
.legend b { color: var(--ink); }

/* outcome chips */
.st-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 650; padding: 2px 10px; border-radius: 99px; white-space: nowrap; }
.st-chip.approved { background: var(--ok-wash); color: var(--ok); } .st-chip.hold { background: var(--hold-wash); color: var(--hold); }
.st-chip.reject { background: var(--rej-wash); color: var(--rej); } .st-chip.signoff { background: var(--sign-wash); color: var(--sign); }
.st-chip.running { background: var(--wash); color: var(--ink-2); }

/* needs-you list */
.needs { background: var(--sheet); border: 1px solid var(--rule); border-radius: 12px; overflow: hidden; margin-bottom: 18px; }
.needs-h { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; padding: 14px 16px 10px; border-bottom: 1px solid var(--rule-2); }
.need { display: grid; grid-template-columns: 5px minmax(0,1.1fr) minmax(0,2fr) auto; gap: 16px; align-items: center; padding: 13px 16px 13px 0; border-bottom: 1px solid var(--rule-2); text-decoration: none !important; color: var(--ink) !important; }
.need:last-child { border-bottom: 0; } .need:hover { background: var(--wash); }
.need .edge { align-self: stretch; border-radius: 0 3px 3px 0; background: var(--hold); } .need.signoff .edge { background: var(--sign); }
.need .who { font-weight: 600; } .need .who small { display: block; font-weight: 400; color: var(--faint); font-size: 13px; }
.need .what { color: var(--body); font-size: 14px; }
.need .go { display: flex; gap: 12px; align-items: center; font-weight: 650; white-space: nowrap; }
.need .btn { border: 1px solid var(--rule); background: var(--card); border-radius: 10px; padding: 4px 12px; font-weight: 400; font-size: 14px; }
.allclear { padding: 18px 16px; color: var(--body); }

/* tables */
.tbl { width: 100%; border-collapse: collapse; background: var(--sheet); border: 1px solid var(--rule); border-radius: 12px; overflow: hidden; font-size: 14.2px; }
.tbl th { font-size: 11.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--rule-2); background: var(--card); }
.tbl td { padding: 10px 14px; border-bottom: 1px solid var(--rule-2); color: var(--body); vertical-align: top; }
.tbl tr:last-child td { border-bottom: 0; }
.tbl .r { text-align: right; white-space: nowrap; } .tbl .sub { font-size: 12.5px; color: var(--faint); }
.tbl a { color: var(--ink); font-weight: 600; text-decoration: none; } .tbl a:hover { color: var(--accent); }
.bad { color: var(--rej); font-weight: 650; }

/* stage tiles */
.rail { display: grid; grid-template-columns: repeat(7, minmax(0,1fr)); gap: 8px; margin: 2px 0 18px !important; padding: 0 !important; list-style: none; }
.rail li, .howbuy li { margin: 0 !important; }
.stage { border: 1px solid var(--rule); border-radius: 12px; background: var(--card); padding: 8.8px 11.2px; color: var(--faint); }
.stage .n { display: block; font-size: 11.2px; font-weight: 700; letter-spacing: .06em; color: var(--faint); }
.stage .nm { display: block; font-size: 14.7px; font-weight: 600; line-height: 1.5; }
.stage .t { display: block; font-size: 11.8px; color: var(--faint); }
.stage.done, .stage.active { background: var(--wash); border-color: var(--accent-line); color: var(--ink); }
.stage.done .n, .stage.active .n { color: var(--accent); }
.stage.active { border-color: var(--accent); box-shadow: 0 0 0 3px var(--wash); }
.stage.active .n { animation: breathe 1.2s ease-in-out infinite; }
.stage.warn { background: var(--hold-wash); border-color: #d9c48a; color: var(--ink); } .stage.warn .n { color: var(--hold); }
.stage.fail { background: var(--rej-wash); border-color: #e3a8b5; color: var(--ink); } .stage.fail .n { color: var(--rej); }
@keyframes breathe { 50% { opacity: .35; } }
@media (max-width: 900px) { .rail { grid-template-columns: repeat(4, minmax(0,1fr)); } }

/* paper trail */
.trail { background: var(--sheet); border: 1px solid var(--rule); border-radius: 12px; padding: 14px 16px 16px; margin-bottom: 18px; overflow-x: auto; }
.tgrid { display: grid; gap: 8px 10px; min-width: min-content; margin-top: 8px; }
.lane { display: flex; flex-direction: column; justify-content: center; padding-right: 8px; border-right: 1px dashed var(--rule); }
.lane b { font-size: 13.5px; font-weight: 600; } .lane span { font-size: 12px; color: var(--faint); }
.ax { display: flex; align-items: center; gap: 8px; position: relative; padding: 4px 0; }
.ax::before { content: ""; position: absolute; left: 0; right: -10px; top: 50%; height: 2px; background: var(--rule); }
.ax .n { position: relative; width: 22px; height: 22px; border-radius: 8px; background: var(--accent); color: #fff; display: grid; place-items: center; font: 700 11.5px var(--display); }
.ax.agent .n { background: var(--ink); }
.ax .d { position: relative; background: var(--sheet); padding: 0 6px; font-size: 12.5px; color: var(--muted); white-space: nowrap; }
.step { display: grid; grid-template-columns: 24px minmax(0,1fr); gap: 8px; background: var(--wash); border: 1px solid var(--accent-line); border-radius: 12px; padding: 8px 10px; }
.step.vendor { background: var(--card); border-color: var(--rule); }
.step .ic { width: 24px; height: 24px; border-radius: 8px; display: grid; place-items: center; font-size: 13px; background: var(--card); color: var(--accent); border: 1px solid var(--accent-line); }
.step.agent .ic { background: var(--ink); color: #fff; border-color: var(--ink); }
.step .st { font-weight: 600; font-size: 13.5px; line-height: 1.3; color: var(--ink); } .step .st a { color: inherit; }
.step .sd { font-size: 12.5px; color: var(--body); margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }

/* decision */
.decision { background: var(--sheet); border: 1px solid var(--rule); border-top: 5px solid var(--faint); border-radius: 12px; padding: 16px 18px; margin-bottom: 14px; }
.decision.approved { border-top-color: var(--ok); } .decision.hold { border-top-color: var(--hold); } .decision.reject { border-top-color: var(--rej); } .decision.signoff { border-top-color: var(--sign); }
.decision .verdict { font-family: var(--display); font-size: 27px; font-weight: 700; line-height: 1.1; }
.decision.approved .verdict { color: var(--ok); } .decision.hold .verdict { color: var(--hold); } .decision.reject .verdict { color: var(--rej); } .decision.signoff .verdict { color: var(--sign); }
.decision .why { font-size: 16px; color: var(--body); margin: 8px 0 10px; line-height: 1.5; }
.facts { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,2fr); gap: 6px 16px; font-size: 14px; padding-top: 10px; border-top: 1px solid var(--rule-2); }
.facts dt { font-size: 11.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); padding-top: 2px; }
.facts dd { margin: 0 !important; color: var(--body); }
.facts { margin: 0 !important; }
.code { font-size: 12px; font-weight: 600; background: var(--pill); color: var(--ink-2); border-radius: 999px; padding: 2px 9px; }

/* panels and the check log */
.panel { background: var(--sheet); border: 1px solid var(--rule); border-radius: 12px; margin-bottom: 14px; }
.panel-h { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; padding: 12px 16px 10px; border-bottom: 1px solid var(--rule-2); }
.panel .pad { padding: 12px 16px; }
.log { list-style: none; margin: 0; padding: 4px 0 8px; }
.log li { display: grid; grid-template-columns: 22px minmax(0,1fr); gap: 10px; padding: 7px 16px; }
.log li.h { display: block; padding: 12px 16px 2px; }
.log .ic { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; font-size: 10.5px; font-weight: 800; color: #fff; background: var(--faint); margin-top: 2px; }
.log .pass .ic { background: transparent; color: var(--ok); border: 1.5px solid var(--ok); }
.log .warn .ic { background: var(--hold); } .log .fail .ic { background: var(--rej); } .log .fail.held .ic { background: var(--hold); }
.log .tt { font-weight: 600; color: var(--ink); } .log .pass .tt { font-weight: 500; }
.log .dd { color: var(--body); font-size: 13.5px; } .log .cd { font-family: var(--mono); font-size: 11.5px; color: var(--faint); margin-left: 6px; }
.ledger { display: flex; height: 10px; gap: 2px; border-radius: 999px; overflow: hidden; background: var(--track); margin: 6px 0 8px; }

/* invoice image */
.desk { background: var(--pill); border: 1px solid var(--rule); border-radius: 12px; padding: 12px; }
.desk img { width: 100%; display: block; border-radius: 2px; box-shadow: 0 1px 0 rgba(46,31,23,.08), 0 10px 26px -10px rgba(46,31,23,.28); }
.desk .lbl { font-size: 13px; color: var(--ink-2); }

/* company records */
.howbuy { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 8px; margin: 0 0 18px !important; padding: 0 !important; list-style: none; }
.howbuy li { background: var(--wash); border: 1px solid var(--accent-line); border-radius: 12px; padding: 9px 12px 10px; }
.howbuy .n { display: block; font-size: 11.2px; font-weight: 700; letter-spacing: .06em; color: var(--accent); }
.howbuy b { display: block; font-size: 14.7px; font-weight: 600; } .howbuy span { font-size: 12.5px; color: var(--faint); }
.orders { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 14px; }
.order { border: 1px solid var(--rule); border-radius: 12px; background: var(--sheet); overflow: hidden; }
.order header { display: flex; justify-content: space-between; gap: 10px; padding: 12px 14px; background: var(--card); border-bottom: 1px solid var(--rule-2); }
.order .tbl { border: 0; border-radius: 0; }
.order header .pill { align-self: flex-start; }
.order footer { padding: 10px 14px; font-size: 13.5px; color: var(--muted); border-top: 1px solid var(--rule-2); }
.mini { display: inline-flex; width: 120px; height: 8px; border-radius: 999px; overflow: hidden; background: var(--track); vertical-align: middle; margin-right: 8px; }
.foot { margin-top: 35px; padding-top: 13px; border-top: 1px solid var(--rule); font-size: 12.5px; color: var(--faint); }
@media (max-width: 900px) { .orders, .howbuy { grid-template-columns: minmax(0,1fr); } }

/* inbox of trails */
.count { font: 600 13px var(--text, inherit); color: var(--faint); background: var(--pill); border-radius: 999px; padding: 1px 9px; margin-left: 6px; vertical-align: 4px; }
.tlist { display: grid; gap: 8px; margin: 2px 0 22px; }
.trow { display: grid; grid-template-columns: minmax(0,1.1fr) minmax(0,1.3fr) minmax(0,2.4fr) minmax(0,1.2fr); gap: 14px; align-items: center;
  background: var(--sheet); border: 1px solid var(--rule); border-radius: 12px; padding: 12px 16px; text-decoration: none !important; color: var(--ink) !important; }
.trow:hover { border-color: var(--accent-line); background: var(--wash); }
.trow.urgent { border-left: 4px solid var(--hold); }
.trow small { display: block; font-size: 12.5px; color: var(--faint); font-weight: 400; margin-top: 2px; }
.trow .tkey b { font-size: 14px; } .trow .tvendor { font-weight: 600; } .trow .twhat { font-size: 14px; color: var(--body); }
.trow .tright { text-align: right; }
@media (max-width: 800px) { .trow { grid-template-columns: minmax(0,1fr); gap: 4px; } .trow .tright { text-align: left; } }

/* timeline */
.ecase .ehead { display: flex; gap: 14px; align-items: flex-start; }
.ecase .enum { flex: none; width: 34px; height: 34px; border-radius: 50%; background: var(--accent); color: #fff;
  display: grid; place-items: center; font-weight: 700; font-size: 15px; }
.ecase .ehead > div:nth-child(2) { flex: 1; min-width: 0; }
.ecase .eout { flex: none; }
.ecase .edl { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 8px 18px; margin: 14px 0 4px 48px; }
.ecase .edl dt { font-size: 12.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--accent); padding-top: 2px; }
.ecase .edl dd { margin: 0; color: var(--body); line-height: 1.55; }
@media (max-width: 760px) { .ecase .edl { grid-template-columns: 1fr; margin-left: 0; } .ecase .ehead { flex-wrap: wrap; } }
.timeline { list-style: none; margin: 0 0 12px !important; padding: 0 !important; position: relative; }
.timeline::before { content: ""; position: absolute; left: 15px; top: 6px; bottom: 6px; width: 2px; background: var(--rule); }
.timeline li { margin: 0 !important; position: relative; }
.timeline a, .timeline li > div { display: grid; grid-template-columns: 32px minmax(0,1fr); gap: 10px; padding: 8px 10px 8px 0;
  border-radius: 10px; text-decoration: none !important; color: var(--ink) !important; }
.timeline a:hover { background: var(--wash); }
.timeline li.sel a { background: var(--wash); box-shadow: inset 3px 0 0 var(--accent); }
.tdot { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; font-size: 14px; position: relative; z-index: 1;
  background: var(--card); border: 1.5px solid var(--rule); }
.tdot.client { border-color: var(--accent-line); color: var(--accent); }
.tdot.vendor { background: var(--pill); color: var(--ink); }
.tdot.agent { background: var(--ink); color: #fff; border-color: var(--ink); }
.tdot.person { border-color: var(--sign); color: var(--sign); }
.tev.k-waiting .tdot { background: var(--hold-wash); border-color: var(--hold); color: var(--hold); font-weight: 800; }
.tbody { display: grid; gap: 1px; min-width: 0; }
.tbody b { font-size: 14px; font-weight: 600; line-height: 1.35; }
.tbody small { font-size: 12.5px; color: var(--body); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.twhen { font-size: 11.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--faint); }
.viewer-h { margin: 0 0 10px; display: grid; gap: 2px; }
.notice-line { font-size: 13.5px; color: var(--body); background: var(--wash); border: 1px solid var(--accent-line); border-radius: 10px; padding: 8px 12px; margin: 6px 0 10px; }

/* Streamlit widgets in the theme */
.stButton > button, .stDownloadButton > button { border-radius: 10px; }
[data-testid="stExpander"] details { border-color: var(--rule); border-radius: 10px; background: var(--card); }
</style>
"""


def apply() -> None:
    st.html(CSS)
