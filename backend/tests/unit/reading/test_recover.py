"""Recovering a total or tax amount the page reader missed, from the PDF's own embedded text.

Only a figure that adds up (taxable value + tax + round-off) and matches the amount in words is taken,
so a planted hidden figure (demo S13) can never fill in a missing total."""
from decimal import Decimal as D

from ap_agent.core.models import Invoice, Line, ParseBlock
from ap_agent.reading.recover import recover_totals

WORDS = "Rupees One Lakh Ninety Five Thousand Eight Hundred Eighty Only"


def blk(text):
    return ParseBlock(page=1, text=text, cls="TextLayer", box=(0.5, 0.6, 0.9, 0.62))


def inter_state(**kw):
    base = dict(supplier_gstin="36AAHFD3381L1Z6", buyer_gstin="29AABCZ5821K1ZW", place_of_supply_state="29",
                taxable_total=D("166000"), igst=D("29880"), round_off=D("0"), grand_total=None, amount_in_words=WORDS,
                lines=[Line(description="MS flat bar 40x6 mm", qty=D("2656"), rate=D("62.50"), taxable=D("166000"),
                            gst_rate=D("18"))])
    base.update(kw)
    return Invoice(**base)


def test_a_missing_total_is_recovered_when_it_adds_up_and_matches_the_words():
    inv, got = recover_totals(inter_state(), [blk("Taxable Value 1,66,000.00"), blk("Invoice Total (Rs.) 1,95,880.00")])
    assert inv.grand_total == D("195880") and got == ["grand_total"]
    assert inv.sources["grand_total"].box == (0.5, 0.6, 0.9, 0.62)


def test_a_hidden_total_that_does_not_add_up_is_ignored():
    inv, got = recover_totals(inter_state(), [blk("Invoice total 29,169.60")])
    assert inv.grand_total is None and got == []


def test_the_total_must_match_the_amount_in_words():
    inv, got = recover_totals(inter_state(amount_in_words="Rupees One Lakh Only"), [blk("Invoice Total 1,95,880.00")])
    assert inv.grand_total is None and got == []


def test_missing_igst_is_recovered_from_the_gst_rate():
    inv, got = recover_totals(inter_state(igst=None, grand_total=D("195880")), [blk("IGST @ 18% 29,880.00")])
    assert inv.igst == D("29880") and got == ["igst"]


def test_missing_cgst_and_sgst_and_total_within_the_state():
    inv = inter_state(supplier_gstin="29AAKFS4417M1ZM", igst=None)
    inv, got = recover_totals(inv, [blk("CGST @ 9% 14,940.00"), blk("SGST @ 9% 14,940.00"),
                                    blk("Invoice Total 1,95,880.00")])
    assert inv.cgst == inv.sgst == D("14940") and inv.grand_total == D("195880")
    assert got == ["cgst", "sgst", "grand_total"]


def test_nothing_is_recovered_without_a_text_layer_or_when_nothing_is_missing():
    assert recover_totals(inter_state(), [])[1] == []
    assert recover_totals(inter_state(grand_total=D("195880")), [blk("Invoice Total 1,95,880.00")])[1] == []
