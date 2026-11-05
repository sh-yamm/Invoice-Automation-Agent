import json
from decimal import Decimal

from ap_agent.ai.agent import run_agent
from ap_agent.ai.helpers import RealAi
from ap_agent.classify.document import classify_document
from ap_agent.classify.transaction import classify_transaction, transaction_signals
from ap_agent.core.config import Settings
from ap_agent.core.models import ParseBlock
from ap_agent.rulebook.loader import load_aop
from factories import FakeAi, FakeGateway, make_invoice, repo

AOP = load_aop(Settings().rulebook_path)


def tool_call(name, args, id_="call-1"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def answer(obj):
    return {"role": "assistant", "content": json.dumps(obj)}


def classify(inv, store, ai=None, gw=None, case_id="c1"):
    store.create_case(case_id, "x.pdf", case_id, None)
    return classify_transaction(inv, repo(), ai or FakeAi(), gw or FakeGateway(), store, case_id, AOP)


# ---------- document type ----------

def test_doc_type_proforma_by_signal_no_llm_call():
    gw = FakeGateway()
    doc, conf, why = classify_document(make_invoice("S11"), [], gw, case_id="c1")
    assert doc == "proforma" and conf == 1.0 and "proforma" in why.lower() and gw.calls == []


def test_doc_type_tax_invoice_by_signal():
    gw = FakeGateway()
    assert classify_document(make_invoice("S01"), [], gw, case_id="c1")[0] == "tax_invoice" and gw.calls == []


def test_doc_type_credit_note_by_negative_total():
    inv = make_invoice("S01", doc_title=None, grand_total=Decimal("-5000"))
    assert classify_document(inv, [], FakeGateway(), case_id="c1")[0] == "credit_note"


def test_doc_type_from_title_block_when_field_missing():
    blocks = [ParseBlock(page=1, text="QUOTATION", box=(0, 0, 1, 1), cls="Title")]
    assert classify_document(make_invoice("S01", doc_title=None), blocks, FakeGateway(), case_id="c1")[0] == "quotation"


def test_doc_type_falls_back_to_model():
    gw = FakeGateway(json_replies=[{"doc_type": "tax_invoice", "confidence": 0.82, "why": "has GSTINs and tax"}])
    doc, conf, _ = classify_document(make_invoice("S01", doc_title=None), [], gw, case_id="c1")
    assert (doc, conf) == ("tax_invoice", 0.82) and gw.calls[0][1] == "fast"


# ---------- transaction type ----------

def test_signals():
    s = transaction_signals(make_invoice("S04"), repo())
    assert s["po_found"] and s["po_type"] == "blanket" and s["contract"] == "CT-901" and s["vendor_id"] == "V003"


def test_txn_recurring_for_po_4490(store):
    assert classify(make_invoice("S04"), store)[:2] == ("recurring", 1.0)


def test_txn_standard_po(store):
    assert classify(make_invoice("S01"), store)[:2] == ("standard_po", 1.0)


def test_txn_po_less_for_telecom(store):
    t, conf, why = classify(make_invoice("S09"), store)
    assert t == "po_less" and conf == 0.95 and "telecom" in why


def test_txn_inferred_po_s08(store):
    ai = FakeAi(po_ranking=[("PO-4507", 0.94, "filing cabinets at the PO rate")])
    t, conf, why = classify(make_invoice("S08"), store, ai=ai)
    assert t == "standard_po" and "PO-4507" in why


def test_txn_po_less_when_nothing_matches_s10(store):
    ai = FakeAi(po_ranking=[("PO-4501", 0.2, "different items")])
    assert classify(make_invoice("S10"), store, ai=ai)[0] == "po_less"


def test_agent_called_when_ambiguous(store):
    ai = FakeAi(po_ranking=[("PO-4507", 0.7, "partly similar")])
    gw = FakeGateway(tool_replies=[tool_call("vendor_lookup", {"gstin": "29AAKFS4417M1ZM"}),
                                   answer({"txn_type": "standard_po", "confidence": 0.86,
                                           "why": "the items are on open PO-4507"})])
    t, conf, why = classify(make_invoice("S10"), store, ai=ai, gw=gw)
    assert (t, conf) == ("standard_po", 0.86)
    calls = store.get_case("c1")["tool_calls"]
    assert calls[0]["tool"] == "vendor_lookup" and calls[0]["result"]["vendor_id"] == "V001"
    second_turn = gw.calls[1][3]
    assert second_turn[-1]["role"] == "tool" and "V001" in second_turn[-1]["content"]


def test_agent_max_turns_gives_uncertain(store):
    ai = FakeAi(po_ranking=[("PO-4507", 0.7, "partly similar")])
    gw = FakeGateway(tool_replies=[tool_call("vendor_lookup", {"gstin": "29AAKFS4417M1ZM"})])
    t, conf, why = classify(make_invoice("S10"), store, ai=ai, gw=gw)
    assert t == "unknown" and conf == 0.0 and "did not reach" in why


def test_run_agent_unknown_tool_is_reported_not_crashing(store):
    store.create_case("c9", "x", "h9", None)
    gw = FakeGateway(tool_replies=[tool_call("delete_everything", {}), answer({"ok": True})])
    out = run_agent(gw, "sys", "user", {}, store=store, case_id="c9", node="t",
                    schema={"type": "object", "required": ["ok"]})
    assert out == {"ok": True}
    assert "unknown tool" in store.get_case("c9")["tool_calls"][0]["result"]["error"]


# ---------- the real AI helpers ----------

def test_real_ai_similarity_uses_embeddings(store):
    gw = FakeGateway(embeddings={"a": [1.0, 0.0], "b": [0.6, 0.8], "c": [1.0, 0.0]})
    ai = RealAi(gw, repo(), store, "c1")
    assert round(ai.similarity("a", "b"), 2) == 0.6 and ai.similarity("a", "c") == 1.0


def test_real_ai_gl_code_drops_unknown_accounts(store):
    gw = FakeGateway(json_replies=[{"options": [
        {"gl_code": "6120", "cost_centre": "CC-IT-BLR", "confidence": 0.93, "why": "telecom"},
        {"gl_code": "9999", "cost_centre": "X", "confidence": 0.5, "why": "made up"}]}])
    out = RealAi(gw, repo(), store, "c1").gl_code(make_invoice("S09"), repo().gl_accounts())
    assert [o[0] for o in out] == ["6120"]


def test_real_ai_rank_po_candidates_prefers_matching_items(store):
    texts = {"Filing cabinet, 4 drawer": [1.0, 0.0], "Ergonomic mesh chair": [0.0, 1.0],
             "Workstation desk 1400mm": [0.1, 0.99]}
    gw = FakeGateway(embeddings=texts)
    ranked = RealAi(gw, repo(), store, "c1").rank_po_candidates(make_invoice("S08"), repo().open_pos("V001"))
    assert ranked[0][0] == "PO-4507" and ranked[0][1] >= 0.9 and ranked[1][1] < 0.5
