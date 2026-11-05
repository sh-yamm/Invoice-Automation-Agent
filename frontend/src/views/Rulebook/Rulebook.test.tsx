import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import { ApiError } from "../../api/client";
import ConnectedData from "../ConnectedData/ConnectedData";
import Rulebook from "./Rulebook";

vi.mock("../../api/client", async (orig) => ({
  ...(await orig<typeof import("../../api/client")>()),
  getAop: vi.fn(), putAop: vi.fn(), listCases: vi.fn(), sendAction: vi.fn(), getData: vi.fn(),
}));

const aop = {
  version: 3, last_edit: { editor: "setup", why: "initial", at: "2026-11-06T00:00:00" },
  authority: { auto_approve_limit_inr: "500000", po_less_auto_limit_inr: "25000", split_window_days: 7 },
  tolerance: { price: { over_pct: "2.0", over_abs_inr: "5000" }, qty_over_ordered_pct: "0", qty_over_received_pct: "0",
               po_balance_over_pct: "0", contract_amount_pct: "0" },
  duplicates: { window_days: 30, min_similarity_pct: 90 },
  confidence: { min_field: 0.85, po_inference_min: 0.9, classification_min: 0.8, gl_coding_min: 0.8 },
  po_less_allowed_categories: ["utilities", "telecom"],
  locked: ["BANK_DETAILS_MISMATCH", "EINVOICE_IRN_MISSING"],
  reasons: [{ code: "BANK_DETAILS_MISMATCH", outcome: "hold", owner: "Vendor master team", explain: "x", next: "y", locked: true },
            { code: "PRICE_VARIANCE", outcome: "hold", owner: "Procurement", explain: "x", next: "y", locked: false }],
};

beforeEach(() => {
  vi.mocked(client.getAop).mockResolvedValue(aop);
  vi.mocked(client.putAop).mockResolvedValue({ ...aop, version: 4 });
  vi.mocked(client.listCases).mockResolvedValue([]);
});

describe("Rulebook", () => {
  it("locked rows have no input", async () => {
    render(<Rulebook />);
    const locked = await screen.findByTestId("locked-BANK_DETAILS_MISMATCH");
    expect(locked.querySelector("input")).toBeNull();
    expect(locked).toHaveTextContent("🔒");
    expect(screen.getByLabelText("Price tolerance (%)")).toHaveValue(2);
  });

  it("save sends changes with why", async () => {
    render(<Rulebook />);
    const price = await screen.findByLabelText("Price tolerance (%)");
    await userEvent.clear(price);
    await userEvent.type(price, "3");
    await userEvent.click(screen.getByRole("button", { name: "Save rulebook" }));
    expect(await screen.findByText(/say why/i)).toBeInTheDocument();
    expect(client.putAop).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Why are you changing it?"), "Steel prices rose this quarter");
    await userEvent.click(screen.getByRole("button", { name: "Save rulebook" }));
    await waitFor(() => expect(client.putAop).toHaveBeenCalledWith({ "tolerance.price.over_pct": 3 }, "AP lead",
                                                                    "Steel prices rose this quarter"));
    expect(await screen.findByText(/Saved as version 4/)).toBeInTheDocument();
  });

  it("422 shows error message", async () => {
    vi.mocked(client.putAop).mockRejectedValue(new ApiError(422, "The list of locked rules cannot be changed."));
    render(<Rulebook />);
    const price = await screen.findByLabelText("Price tolerance (%)");
    await userEvent.clear(price);
    await userEvent.type(price, "4");
    await userEvent.type(screen.getByLabelText("Why are you changing it?"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Save rulebook" }));
    expect(await screen.findByText("The list of locked rules cannot be changed.")).toBeInTheDocument();
  });
});

describe("ConnectedData", () => {
  it("shows the PO ledger with usage", async () => {
    vi.mocked(client.getData).mockResolvedValue([{ po_number: "PO-4490", vendor: "Nimbus IT Services LLP",
      po_type: "blanket", value: "660000.00", invoiced: "600000.00", remaining: "60000.00", used_pct: 90.9 }]);
    render(<ConnectedData />);
    expect(await screen.findByText("PO-4490")).toBeInTheDocument();
    expect(screen.getByText("₹6,60,000.00")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /91% used/ })).toBeInTheDocument();
  });
});
