"""The LangGraph graph for one invoice, and the runner the API uses to start and resume cases."""
from __future__ import annotations

import shutil
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from ap_agent.ai.helpers import RealAi
from ap_agent.core.models import Outcome, Status
from ap_agent.erp.repository import Repository
from ap_agent.pipeline import nodes as n
from ap_agent.pipeline.events import EventBus
from ap_agent.pipeline.state import CaseState
from ap_agent.reading.pdfinfo import inspect_pdf
from ap_agent.rulebook.loader import load_aop


class ActionError(ValueError):
    """A human action that isn't allowed for this case right now."""


@dataclass
class Deps:
    repo: Repository
    store: object
    aop_path: Path
    gateway: object
    files_dir: Path
    checkpoint_path: Path
    pace_ms: int = 0
    erp_dir: Path | None = None
    bus: EventBus | None = None
    ai_factory: object = None
    _ai: dict = field(default_factory=dict)

    def __post_init__(self):
        self.files_dir = Path(self.files_dir)
        self.bus = self.bus or EventBus(self.store, self.pace_ms)

    def ai_for(self, state):
        cid = state["case_id"]
        if cid not in self._ai:
            make = self.ai_factory or (lambda case_id, sample_id: RealAi(self.gateway, self.repo, self.store, case_id,
                                                                         cache_prefix=sample_id))
            self._ai[cid] = make(cid, state.get("sample_id"))
        return self._ai[cid]

    def reload(self):
        """Re-read the ERP files (e.g. a goods receipt arrived) before a re-check."""
        if self.erp_dir:
            self.repo = Repository.load(self.erp_dir)


def build_graph(deps: Deps, checkpointer):
    g = StateGraph(CaseState)
    for name, fn in [("ingest", n.ingest), ("render", n.render), ("parse", n.parse), ("reconcile", n.reconcile),
                     ("extract", n.extract), ("ground", n.ground_node), ("classify_document", n.classify_document_node),
                     ("classify_transaction", n.classify_transaction_node), ("validate", n.validate),
                     ("standard_po", n.standard_po), ("recurring", n.recurring), ("po_less", n.po_less),
                     ("controls", n.controls), ("completeness_guard", n.guard), ("decide", n.decide),
                     ("human_gate", n.human_gate), ("finalise", n.finalise)]:
        g.add_node(name, (lambda f: lambda state: f(state, deps))(fn))

    stop_or = lambda nxt: (lambda s: "decide" if s.get("stopped") else nxt)
    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", stop_or("render"), ["decide", "render"])
    g.add_conditional_edges("render", stop_or("parse"), ["decide", "parse"])
    g.add_conditional_edges("parse", stop_or("reconcile"), ["decide", "reconcile"])
    g.add_edge("reconcile", "extract")
    g.add_conditional_edges("extract", stop_or("ground"), ["decide", "ground"])
    g.add_edge("ground", "classify_document")
    g.add_conditional_edges("classify_document", stop_or("classify_transaction"), ["decide", "classify_transaction"])
    g.add_conditional_edges("classify_transaction", stop_or("validate"), ["decide", "validate"])
    g.add_conditional_edges("validate", lambda s: s["txn_type"], ["standard_po", "recurring", "po_less"])
    g.add_edge("standard_po", "controls")
    g.add_edge("recurring", "controls")
    g.add_conditional_edges("po_less", lambda s: "standard_po" if s.get("rerouted") and s.get("txn_type") == "standard_po"
                            else "controls", ["standard_po", "controls"])
    g.add_edge("controls", "completeness_guard")
    g.add_edge("completeness_guard", "decide")
    g.add_conditional_edges("decide", lambda s: "finalise" if s["outcome"] in (int(Outcome.APPROVED), int(Outcome.REJECTED))
                            else "human_gate", ["finalise", "human_gate"])

    def after_human(s):
        kind = (s.get("action") or {}).get("action")
        if kind in ("confirm_field", "recheck"):
            return "validate" if s.get("txn_type") else "classify_transaction"
        if kind == "ask_vendor":
            return "human_gate"
        return "finalise"
    g.add_conditional_edges("human_gate", after_human, ["validate", "classify_transaction", "human_gate", "finalise"])
    g.add_edge("finalise", END)
    return g.compile(checkpointer=checkpointer)


ALLOWED = {
    Outcome.ON_HOLD: {"approve_anyway", "reject", "ask_vendor", "confirm_field", "recheck"},
    Outcome.NEEDS_SIGNOFF: {"sign_off", "reject", "ask_vendor", "recheck"},
}


class Pipeline:
    def __init__(self, deps: Deps):
        self.deps = deps
        Path(deps.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(deps.checkpoint_path), check_same_thread=False)
        self.app = build_graph(deps, SqliteSaver(conn))
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)

    def _config(self, case_id):
        return {"configurable": {"thread_id": case_id}, "recursion_limit": 60}

    def prepare(self, case_id: str, pdf_path: Path, sample_id: str | None = None, filename: str | None = None) -> None:
        """Store the file and create the case record (so the UI can open it before the run starts)."""
        folder = self.deps.files_dir / case_id
        folder.mkdir(parents=True, exist_ok=True)
        original = folder / "original.pdf"
        shutil.copyfile(pdf_path, original)
        info = inspect_pdf(original)
        self.deps.store.create_case(case_id, filename or Path(pdf_path).name, info["sha256"], sample_id)

    def run(self, case_id: str) -> dict:
        case = self.deps.store.get_case(case_id)
        original = self.deps.files_dir / case_id / "original.pdf"
        with self._locks[case_id]:
            self.app.invoke({"case_id": case_id, "pdf_path": str(original), "sample_id": case["sample_id"],
                             "findings": [], "stopped": False}, self._config(case_id))
        return self.deps.store.get_case(case_id)

    def start(self, case_id: str, pdf_path: Path, sample_id: str | None = None, filename: str | None = None) -> dict:
        self.prepare(case_id, pdf_path, sample_id, filename)
        return self.run(case_id)

    def check_action(self, case: dict, action: dict) -> None:
        if case is None:
            raise ActionError("No such case.")
        if case["status"] not in ("waiting", "waiting_vendor"):
            raise ActionError("This case is not waiting for a person.")
        kind = action.get("action")
        if kind not in ALLOWED.get(case["outcome"], set()):
            raise ActionError(f"'{kind}' is not available for a case that is {case['outcome'].name.lower()}.")
        aop = load_aop(self.deps.aop_path)
        locked = {f.code for f in case["findings"] if f.status is Status.FAIL and f.code in aop.locked}
        if kind == "approve_anyway" and locked and not (action.get("note") or "").strip():
            raise ActionError(f"Approving over {', '.join(sorted(locked))} needs a verification note.")
        if kind == "confirm_field" and not (action.get("field") and action.get("value")):
            raise ActionError("Say which field to confirm and its value.")

    def resume(self, case_id: str, action: dict) -> dict:
        with self._locks[case_id]:
            case = self.deps.store.get_case(case_id)
            self.check_action(case, action)
            fresh = self.deps.store.add_human_action(case_id, action["action"], action.get("actor", "a person"),
                                                     action.get("note"), {k: v for k, v in action.items()
                                                                          if k not in ("action_key",)},
                                                     action_key=action.get("action_key") or action["action"])
            if fresh:
                self.app.invoke(Command(resume=action), self._config(case_id))
        return self.deps.store.get_case(case_id)
