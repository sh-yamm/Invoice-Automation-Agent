# Scripts, in the order they run

None of these run while the app is serving. They build the data the app starts from. Run them from the
repository root with Python 3.11. Steps 2–5 only need re-running when the demo invoices or the history change.

| # | Script | What it does | Writes |
|---|---|---|---|
| 1 | `scripts/make_gstins.py` | Prints valid GSTINs (with the right check digit) for new test vendors. | nothing (prints) |
| 2 | `samples/generate.py` | Prints the 16 demo invoice PDFs from `samples/specs.py`. | `samples/pdf/` |
| 3 | `samples/seed_cache.py` | Runs each demo invoice through the agent once with live models and records every model reply, so demos replay the same answers for free. | `samples/cache/` |
| 4 | `scripts/make_seed_history.py` | Lists the 38 past invoices: numbers, dates and totals the dashboard shows. | `data/seed/history.json` |
| 5 | `scripts/build_history.py` | Prints those 38 invoices, ties each to its PO and goods receipt, runs them through the agent in date order, and saves the result. A demo reset restores it. | `data/erp/` (their POs and receipts), `data/seed/history.db`, `checkpoints.db`, `files/`, `cache/` |
| 6 | `scripts/smoke.sh` | Checks a running API: resets the demo, runs S01, expects it approved. | nothing |

The app itself starts at `streamlit_app.py`; the code path of one invoice through the agent is listed in
`backend/src/ap_agent/pipeline/nodes.py`, one stage file per step under `pipeline/steps/`.
