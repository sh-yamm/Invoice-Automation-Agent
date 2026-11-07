import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { CaseSummary, Kpis, Sample } from "../../api/types";
import WorkQueue from "./WorkQueue";

vi.mock("../../api/client", () => ({
  listCases: vi.fn(),
  getKpis: vi.fn(),
  getSamples: vi.fn(),
  createCase: vi.fn(),
  resetDemo: vi.fn(),
}));

const base: CaseSummary = {
  case_id: "C-1", created_at: "2026-11-05T10:00:00", filename: "a.pdf", sample_id: null, status: "done",
  vendor_id: "V001", vendor_name: "Shree Ganesh Office Furniture", invoice_no: "SGOF/26-27/0412",
  invoice_date: "2026-10-29", grand_total: "284380.00", doc_type: "tax_invoice", txn_type: "standard_po",
  txn_confidence: 1, txn_why: "", outcome: 0, outcome_label: "Approved", primary_code: "ALL_CHECKS_PASSED",
  why: "Every required check passed.", owner: "No one", next_step: "", also: [], agent_note: null,
  decided_at: "2026-11-05T10:00:40", is_seed: 0,
};
const cases: CaseSummary[] = [
  base,
  { ...base, case_id: "C-2", vendor_name: "Nimbus IT Services LLP", txn_type: "recurring", outcome: 2,
    outcome_label: "On hold", primary_code: "PERIOD_ALREADY_BILLED", status: "waiting", why: "October already billed." },
  { ...base, case_id: "C-3", vendor_name: "Namma Fibernet Pvt Ltd", txn_type: "po_less", outcome: 1,
    outcome_label: "Needs sign-off", primary_code: "NEEDS_SIGNOFF", status: "waiting" },
];
const kpis: Kpis = {
  processed: 47, total_inr: "3860000", touchless: 32, touchless_pct: 68, exceptions: 15, protected_inr: "167425",
  protected_cases: 2, avg_handling_seconds: 38, outcomes: { approved: 32, needs_signoff: 3, on_hold: 9, rejected: 3 },
  by_type: { standard_po: 40, recurring: 5, po_less: 2 },
  touchless_series: Array.from({ length: 7 }, (_, i) => ({ date: `2026-11-0${i + 1}`, cases: 5, touchless_pct: 60 + i })),
};
const samples: Sample[] = [{ id: "S01", title: "Clean invoice, everything matches", blurb: "Auto-approved",
  layout: "classic", scanned: false, vendor: "Shree Ganesh", total: "284380", expected_outcome: 0,
  expected_code: "ALL_CHECKS_PASSED" }];

beforeEach(() => {
  vi.mocked(client.listCases).mockResolvedValue(cases);
  vi.mocked(client.getKpis).mockResolvedValue(kpis);
  vi.mocked(client.getSamples).mockResolvedValue(samples);
  vi.mocked(client.createCase).mockResolvedValue({ case_id: "C-NEW" });
  window.location.hash = "";
});

const table = () => within(screen.getByRole("table"));

describe("WorkQueue", () => {
  it("renders rows from listCases", async () => {
    render(<WorkQueue />);
    expect(await table().findByText("Nimbus IT Services LLP")).toBeInTheDocument();
    expect(table().getByText("Shree Ganesh Office Furniture")).toBeInTheDocument();
    expect(table().getAllByText("₹2,84,380.00")).toHaveLength(3);
    expect(screen.getByText("68%")).toBeInTheDocument();
  });

  it("leads with the invoices waiting for a person", async () => {
    render(<WorkQueue />);
    expect(await screen.findByRole("heading", { name: "2 invoices need you" })).toBeInTheDocument();
    const needs = within(screen.getByRole("region", { name: "Needs a person" }));
    expect(needs.getByText("Nimbus IT Services LLP")).toBeInTheDocument();
    expect(needs.getByText("Namma Fibernet Pvt Ltd")).toBeInTheDocument();
    expect(needs.queryByText("Shree Ganesh Office Furniture")).not.toBeInTheDocument();
  });

  it("shows this week's numbers first and can switch to all time", async () => {
    render(<WorkQueue />);
    await table().findByText("Nimbus IT Services LLP");
    expect(client.getKpis).toHaveBeenCalledWith(7);
    expect(screen.getByRole("heading", { name: "This week" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "All time" }));
    await waitFor(() => expect(client.getKpis).toHaveBeenCalledWith(undefined));
  });

  it("type filter narrows rows", async () => {
    render(<WorkQueue />);
    await table().findByText("Nimbus IT Services LLP");
    await userEvent.click(screen.getByRole("button", { name: /^Recurring/ }));
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText("Nimbus IT Services LLP")).toBeInTheDocument();
  });

  it("outcome tabs narrow rows", async () => {
    render(<WorkQueue />);
    await table().findByText("Nimbus IT Services LLP");
    await userEvent.click(screen.getByRole("tab", { name: /Awaiting sign-off/ }));
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(within(rows[0]).getByText("Namma Fibernet Pvt Ltd")).toBeInTheDocument();
  });

  it("clicking a sample calls createCase and navigates", async () => {
    render(<WorkQueue />);
    await userEvent.click(await screen.findByRole("button", { name: "Process an invoice" }));
    await userEvent.click(await screen.findByRole("button", { name: /Clean invoice, everything matches/ }));
    await waitFor(() => expect(client.createCase).toHaveBeenCalledWith({ sampleId: "S01", pace: "normal" }));
    expect(window.location.hash).toBe("#case-C-NEW");
  });

  it("run speed chosen in the panel is sent with the case", async () => {
    render(<WorkQueue />);
    await userEvent.click(await screen.findByRole("button", { name: "Process an invoice" }));
    await userEvent.click(screen.getByRole("button", { name: "Slow, for presenting" }));
    await userEvent.click(await screen.findByRole("button", { name: /Clean invoice, everything matches/ }));
    await waitFor(() => expect(client.createCase).toHaveBeenCalledWith({ sampleId: "S01", pace: "presenter" }));
  });

  it("clicking a row opens the case", async () => {
    render(<WorkQueue />);
    await userEvent.click(await table().findByText("Nimbus IT Services LLP"));
    expect(window.location.hash).toBe("#case-C-2");
  });
});
