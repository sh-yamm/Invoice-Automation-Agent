"""Read-only lookup tools the agent may call. None of them can change anything."""
from __future__ import annotations


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties,
                                                            "required": required}}}


def classification_tools(repo, ai) -> dict:
    def vendor_lookup(gstin: str):
        v = repo.vendor_by_gstin(gstin)
        if not v:
            return {"found": False, "gstin": gstin}
        return {"found": True, "vendor_id": v.vendor_id, "name": v.name, "category": v.category, "status": v.status}

    def po_search(vendor_id: str, text: str = ""):
        out = []
        for po in repo.open_pos(vendor_id):
            score = max((ai.similarity(text, l.description) for l in po.lines), default=0.0) if text else None
            out.append({"po_number": po.po_number, "po_type": po.po_type, "po_date": po.po_date.isoformat(),
                        "value": str(po.value), "match": round(score, 2) if score is not None else None,
                        "lines": [{"line": l.line_no, "description": l.description, "qty": str(l.qty),
                                   "unit": l.unit, "rate": str(l.rate)} for l in po.lines]})
        return {"vendor_id": vendor_id, "open_pos": out}

    def contract_lookup(vendor_id: str):
        c = repo.contract_for(vendor_id, None)
        if not c:
            return {"found": False}
        return {"found": True, "contract_id": c.contract_id, "po_number": c.po_number, "start": c.start_date.isoformat(),
                "end": c.end_date.isoformat(), "cycle": c.billing_cycle, "amount_per_period": str(c.amount_per_period)}

    return {
        "vendor_lookup": (_fn("vendor_lookup", "Look up a vendor in the vendor master by GSTIN.",
                              {"gstin": {"type": "string"}}, ["gstin"]), vendor_lookup),
        "po_search": (_fn("po_search", "List a vendor's open purchase orders, scored against an item description.",
                          {"vendor_id": {"type": "string"}, "text": {"type": "string"}}, ["vendor_id"]), po_search),
        "contract_lookup": (_fn("contract_lookup", "Find a recurring contract for a vendor.",
                                {"vendor_id": {"type": "string"}}, ["vendor_id"]), contract_lookup),
    }
