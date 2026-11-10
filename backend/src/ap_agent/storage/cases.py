"""The case record store: everything that happened to each invoice."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ap_agent.core.models import Finding, Outcome
from ap_agent.storage.db import Db
from ap_agent.storage.ledgers import History, Ledger


def _now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def _dumps(v) -> str:
    def default(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if hasattr(o, "model_dump"):
            return o.model_dump(mode="json")
        return str(o)
    return json.dumps(v, default=default, ensure_ascii=False)


class Store:
    def __init__(self, path: Path):
        self.db = Db(path)
        self.ledger = Ledger(self.db)
        self.history = History(self.db)

    # ---------- cases ----------
    def create_case(self, case_id: str, filename: str | None, sha256: str | None, sample_id: str | None,
                    created_at: str | None = None, is_seed: bool = False, assigned_po: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO cases (case_id, created_at, filename, sha256, sample_id, is_seed, assigned_po) "
            "VALUES (?,?,?,?,?,?,?)",
            (case_id, created_at or _now(), filename, sha256, sample_id, int(is_seed), assigned_po))

    def set_assigned_po(self, case_id: str, po: str | None) -> None:
        """The purchase order a person said this invoice is for (None: let the agent find it)."""
        self.db.execute("UPDATE cases SET assigned_po = ? WHERE case_id = ?", (po, case_id))

    # ---------- changes people make to the company records ----------
    def add_record_change(self, kind: str, ref: str | None, actor: str, why: str, payload: dict) -> None:
        self.db.execute("INSERT INTO record_changes (at, kind, ref, actor, why, payload) VALUES (?,?,?,?,?,?)",
                        (_now(), kind, ref, actor, why, _dumps(payload)))

    def record_changes(self, ref: str | None = None) -> list[dict]:
        sql = "SELECT * FROM record_changes" + (" WHERE ref = ?" if ref else "") + " ORDER BY seq DESC"
        return [{**dict(r), "payload": json.loads(r["payload"] or "{}")} for r in self.db.query(sql, (ref,) if ref else ())]

    def set_status(self, case_id: str, status: str) -> None:
        self.db.execute("UPDATE cases SET status = ? WHERE case_id = ?", (status, case_id))

    def set_invoice_summary(self, case_id: str, *, vendor_id, vendor_name, invoice_no, invoice_no_norm,
                            invoice_date: date | None, grand_total: Decimal | None, line_texts: list[str],
                            period_start: date | None, invoice_json: str | None = None) -> None:
        self.db.execute(
            """UPDATE cases SET vendor_id=?, vendor_name=?, invoice_no=?, invoice_no_norm=?, invoice_date=?,
               grand_total=?, line_texts=?, period_start=?, invoice_json=COALESCE(?, invoice_json) WHERE case_id=?""",
            (vendor_id, vendor_name, invoice_no, invoice_no_norm,
             invoice_date.isoformat() if invoice_date else None,
             str(grand_total) if grand_total is not None else None, _dumps(line_texts),
             period_start.isoformat() if period_start else None, invoice_json, case_id))

    def set_classification(self, case_id: str, doc_type: str | None, txn_type: str | None,
                           confidence: float | None, why: str | None) -> None:
        self.db.execute("UPDATE cases SET doc_type=?, txn_type=?, txn_confidence=?, txn_why=? WHERE case_id=?",
                        (doc_type, txn_type, confidence, why, case_id))

    def set_outcome(self, case_id: str, outcome: Outcome, primary_code: str | None, why: str, owner: str,
                    next_step: str, agent_note: str | None, txn_type: str | None, doc_type: str | None,
                    also: list[str] | None = None, aop_version: int | None = None,
                    decided_at: str | None = None, status: str | None = None) -> None:
        if status is None:
            status = "done" if outcome in (Outcome.APPROVED, Outcome.REJECTED) else "waiting"
        self.db.execute(
            """UPDATE cases SET outcome=?, primary_code=?, why=?, owner=?, next_step=?, agent_note=?,
               txn_type=COALESCE(?, txn_type), doc_type=COALESCE(?, doc_type), also=?,
               aop_version=COALESCE(?, aop_version), decided_at=?, status=? WHERE case_id=?""",
            (int(outcome), primary_code, why, owner, next_step, agent_note, txn_type, doc_type,
             _dumps(also or []), aop_version, decided_at or _now(), status, case_id))

    def case_status(self, case_id: str) -> str | None:
        rows = self.db.query("SELECT status FROM cases WHERE case_id = ?", (case_id,))
        return rows[0]["status"] if rows else None

    def case_by_sha(self, sha256: str, exclude_case: str) -> str | None:
        rows = self.db.query("SELECT case_id FROM cases WHERE sha256 = ? AND case_id != ? ORDER BY created_at",
                             (sha256, exclude_case))
        return rows[0]["case_id"] if rows else None

    # ---------- child records ----------
    def add_finding(self, case_id: str, finding: Finding) -> None:
        seq = self.db.next_seq("findings", case_id)
        self.db.execute("INSERT INTO findings VALUES (?,?,?,?)", (case_id, seq, finding.id, finding.model_dump_json()))

    def clear_findings(self, case_id: str) -> None:
        self.db.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))

    def add_event(self, case_id: str, type: str, payload: dict) -> int:
        seq = self.db.next_seq("events", case_id)
        self.db.execute("INSERT INTO events VALUES (?,?,?,?,?)", (case_id, seq, _now(), type, _dumps(payload)))
        return seq

    def add_tool_call(self, case_id: str, node: str, tool: str, args, result) -> None:
        seq = self.db.next_seq("tool_calls", case_id)
        self.db.execute("INSERT INTO tool_calls VALUES (?,?,?,?,?,?,?)",
                        (case_id, seq, _now(), node, tool, _dumps(args), _dumps(result)))

    def add_llm_call(self, case_id: str, node: str, model: str, prompt, response, reasoning: str | None,
                     latency_ms: int, tokens: int | None) -> None:
        seq = self.db.next_seq("llm_calls", case_id)
        self.db.execute("INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (case_id, seq, _now(), node, model, _dumps(prompt), _dumps(response), reasoning,
                         latency_ms, tokens))

    def add_human_action(self, case_id: str, action: str, actor: str, note: str | None, payload: dict,
                         action_key: str) -> bool:
        cur = self.db.execute("INSERT OR IGNORE INTO human_actions VALUES (?,?,?,?,?,?,?)",
                              (case_id, action_key, _now(), action, actor, note, _dumps(payload)))
        return cur.rowcount == 1

    # ---------- ledgers ----------
    def ledger_write(self, case_id: str, po_number: str, line_no: int, qty: Decimal, amount: Decimal) -> None:
        self.db.execute("INSERT OR REPLACE INTO po_ledger VALUES (?,?,?,?,?)",
                        (case_id, po_number, line_no, str(qty), str(amount)))

    def period_write(self, case_id: str, contract_id: str, period_start: date) -> None:
        self.db.execute("INSERT OR IGNORE INTO period_ledger VALUES (?,?,?)",
                        (case_id, contract_id, period_start.isoformat()))

    # ---------- reads ----------
    def _case_row(self, r) -> dict:
        d = dict(r)
        d["outcome"] = Outcome(d["outcome"]) if d["outcome"] is not None else None
        d["line_texts"] = json.loads(d["line_texts"] or "[]")
        d["also"] = json.loads(d["also"] or "[]")
        return d

    def get_case(self, case_id: str) -> dict | None:
        rows = self.db.query("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        if not rows:
            return None
        case = self._case_row(rows[0])
        q = lambda t: self.db.query(f"SELECT * FROM {t} WHERE case_id = ? ORDER BY seq", (case_id,))
        case["findings"] = [Finding.model_validate_json(r["json"]) for r in q("findings")]
        case["events"] = [{"seq": r["seq"], "at": r["at"], "type": r["type"], "payload": json.loads(r["payload"])}
                          for r in q("events")]
        case["tool_calls"] = [{**dict(r), "args": json.loads(r["args"]), "result": json.loads(r["result"])}
                              for r in q("tool_calls")]
        case["llm_calls"] = [{**dict(r), "prompt": json.loads(r["prompt"]), "response": json.loads(r["response"])}
                             for r in q("llm_calls")]
        case["human_actions"] = [{**dict(r), "payload": json.loads(r["payload"] or "{}")} for r in
                                 self.db.query("SELECT * FROM human_actions WHERE case_id = ? ORDER BY at", (case_id,))]
        return case

    def list_cases(self, filters: dict) -> list[dict]:
        sql, params = "SELECT * FROM cases WHERE 1=1", []
        for key in ("outcome", "txn_type", "owner", "status", "vendor_id"):
            if filters.get(key) is not None:
                sql += f" AND {key} = ?"
                v = filters[key]
                params.append(int(v) if isinstance(v, Outcome) else v)
        sql += " ORDER BY created_at DESC"
        return [self._case_row(r) for r in self.db.query(sql, params)]

    def events_since(self, case_id: str, after_seq: int) -> list[dict]:
        rows = self.db.query("SELECT * FROM events WHERE case_id = ? AND seq > ? ORDER BY seq", (case_id, after_seq))
        return [{"seq": r["seq"], "at": r["at"], "type": r["type"], "payload": json.loads(r["payload"])} for r in rows]
