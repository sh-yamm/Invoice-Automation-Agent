import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { CaseDetail, CaseEvent, Finding } from "../../api/types";
import LiveCase from "./LiveCase";

vi.mock("../../api/client", () => ({ getCase: vi.fn(), streamEvents: vi.fn(), sendAction: vi.fn() }));

let emit: (e: CaseEvent) => void = () => undefined;
let end: () => void = () => undefined;

const f = (over: Partial<Finding>): Finding => ({
  id: Math.random().toString(16).slice(2, 10), check: "c", stage: "validate", status: "pass", code: null, outcome: null,
  title: "ok", detail: "", evidence: [], data: {}, stop: false, ...over,
});

const base: CaseDetail = {
  case_id: "C-1", created_at: "2026-11-06T10:00:00", filename: "S03.pdf", sample_id: "S03", status: "waiting",
  vendor_id: "V002", vendor_name: "Kaveri Packaging Industries", invoice_no: "KPI/26-27/1187",
  invoice_date: "2026-10-31", grand_total: "109150.00", doc_type: "tax_invoice", txn_type: "standard_po",
  txn_confidence: 1, txn_why: "PO-4522 is printed on the invoice", outcome: 2, outcome_label: "On hold",
  primary_code: "BANK_DETAILS_MISMATCH", why: "The invoice asks for payment to HDFC Bank A/c ****4471.",
  owner: "Vendor master team", next_step: "Call the vendor on the number on file.", also: [], agent_note: "No extra risk.",
  decided_at: "2026-11-06T10:00:30", is_seed: 0, invoice: null, findings: [], tool_calls: [],
  llm_calls: [{ node: "agent_review", model: "nvidia/nemotron-3-ultra-550b-a55b (cached)", reasoning: "Thinking about the bank change…", latency_ms: 0, at: "" }],
  human_actions: [], file: "/api/cases/C-1/file", pages: ["/api/cases/C-1/pages/1.png"], locked_codes: ["BANK_DETAILS_MISMATCH"],
};

beforeEach(() => {
  vi.mocked(client.streamEvents).mockImplementation((_id, onEvent, onEnd) => {
    emit = onEvent;
    end = onEnd ?? (() => undefined);
    return () => undefined;
  });
});

describe("LiveCase", () => {
  it("findings appear in order", async () => {
    vi.mocked(client.getCase).mockResolvedValue({ ...base, status: "running", outcome: null });
    render(<LiveCase caseId="C-1" />);
    await waitFor(() => expect(client.streamEvents).toHaveBeenCalled());
    act(() => {
      emit({ type: "node_started", seq: 0, payload: { node: "ingest" } });
      emit({ type: "finding", seq: 1, payload: f({ title: "Readable PDF, 1 page(s)" }) as never });
      emit({ type: "finding", seq: 2, payload: f({ title: "Bank account differs from the vendor master", status: "fail", code: "BANK_DETAILS_MISMATCH", outcome: 2 }) as never });
    });
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items.findIndex((t) => t?.includes("Readable PDF"))).toBeLessThan(items.findIndex((t) => t?.includes("Bank account differs")));
  });

  it("hover highlights evidence box", async () => {
    vi.mocked(client.getCase).mockResolvedValue(base);
    render(<LiveCase caseId="C-1" />);
    await waitFor(() => expect(client.streamEvents).toHaveBeenCalled());
    act(() => emit({ type: "finding", seq: 1, payload: f({ id: "ev1", title: "Bank details differ", status: "fail",
      evidence: [{ field: "bank_account", page: 1, box: [0.1, 0.4, 0.5, 0.42], text: "HDFC" }] }) as never }));
    const box = await screen.findByTestId("box-ev1-0");
    expect(box).not.toHaveClass("hl");
    await userEvent.hover(screen.getByText("Bank details differ"));
    expect(box).toHaveClass("hl");
  });

  it("approve anyway on locked code requires note", async () => {
    vi.mocked(client.getCase).mockResolvedValue(base);
    vi.mocked(client.sendAction).mockResolvedValue({ ...base, status: "done", outcome: 0, outcome_label: "Approved",
      primary_code: "APPROVED_BY_PERSON", why: "Approved by AP reviewer after review." });
    render(<LiveCase caseId="C-1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Approve anyway" }));
    expect(screen.getByText(/verification note/i)).toBeInTheDocument();
    expect(client.sendAction).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/Note/), "Called on the number on file; confirmed.");
    await userEvent.click(screen.getByRole("button", { name: "Approve anyway" }));
    await waitFor(() => expect(client.sendAction).toHaveBeenCalledWith("C-1", expect.objectContaining({
      action: "approve_anyway", note: "Called on the number on file; confirmed." })));
  });

  it("confirm field sends action and re-renders decision", async () => {
    const low = f({ title: "Unsure about invoice date", status: "fail", code: "LOW_CONFIDENCE_FIELD", outcome: 2,
      check: "field_confidence", data: { values: { invoice_date: "2026-11-02" } } });
    const held = { ...base, primary_code: "LOW_CONFIDENCE_FIELD", locked_codes: [], findings: [low],
      why: "I could not read the invoice date with enough confidence (71%)." };
    vi.mocked(client.getCase).mockResolvedValue(held);
    vi.mocked(client.sendAction).mockResolvedValue({ ...held, status: "done", outcome: 0, outcome_label: "Approved",
      primary_code: "ALL_CHECKS_PASSED", why: "Every required check passed." });
    render(<LiveCase caseId="C-1" />);
    const input = await screen.findByLabelText("invoice date");
    await userEvent.clear(input);
    await userEvent.type(input, "02/11/2026");
    await userEvent.click(screen.getByRole("button", { name: /Confirm and continue/ }));
    await waitFor(() => expect(client.sendAction).toHaveBeenCalledWith("C-1", expect.objectContaining({
      action: "confirm_field", field: "invoice_date", value: "02/11/2026" })));
    expect(await screen.findByText("Every required check passed.")).toBeInTheDocument();
  });

  it("shows classification and replay badge", async () => {
    vi.mocked(client.getCase).mockResolvedValue(base);
    render(<LiveCase caseId="C-1" />);
    expect(await screen.findByText(/Classified as Standard PO/)).toBeInTheDocument();
    expect(screen.getByText(/Recorded model replies/)).toBeInTheDocument();
    act(() => end());
  });
});
