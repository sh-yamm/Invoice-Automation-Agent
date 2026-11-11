"""The state LangGraph carries for one invoice. Everything is plain JSON so checkpoints stay portable."""
from __future__ import annotations

from typing import TypedDict


class CaseState(TypedDict, total=False):
    case_id: str
    pdf_path: str
    sample_id: str | None
    assigned_po: str | None  # the PO a person uploaded the invoice to (None: let the agent find it)
    pdf_info: dict
    same_file_case: dict | None
    pages: list[str]
    text_blocks: list[dict]
    parse_blocks: list[dict]
    invoice: dict | None
    doc_type: str | None
    doc_confidence: float
    doc_why: str
    txn_type: str | None
    txn_confidence: float
    txn_why: str
    rerouted: bool
    match: dict            # po_number, pairs, contract_id, gl, conv
    findings: list[dict]   # every finding so far (Finding.model_dump(mode="json"))
    stopped: bool          # a blocking stop before matching: go straight to the decision
    aop_version: int
    outcome: int | None
    verdict: dict | None
    agent_note: str | None
    agent_reasoning: str | None
    action: dict | None
    restart: bool          # a re-check after a failed run starts the case from the beginning
