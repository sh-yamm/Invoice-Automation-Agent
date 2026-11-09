// Mirrors the backend JSON (ap_agent/api). Money arrives as exact decimal strings.

export type Outcome = 0 | 1 | 2 | 3; // approved, needs sign-off, on hold, rejected
export type TxnType = "standard_po" | "recurring" | "po_less";
export type Status = "running" | "waiting" | "waiting_vendor" | "done";

export interface Evidence {
  field: string;
  page: number | null;
  box: [number, number, number, number] | null;
  text: string | null;
}

export interface Finding {
  id: string;
  check: string;
  stage: string;
  status: "pass" | "warn" | "fail";
  code: string | null;
  outcome: Outcome | null;
  title: string;
  detail: string;
  evidence: Evidence[];
  data: Record<string, unknown>;
  stop: boolean;
}

export interface CaseSummary {
  case_id: string;
  created_at: string;
  filename: string | null;
  sample_id: string | null;
  status: Status;
  vendor_id: string | null;
  vendor_name: string | null;
  invoice_no: string | null;
  invoice_date: string | null;
  grand_total: string | null;
  doc_type: string | null;
  txn_type: TxnType | null;
  txn_confidence: number | null;
  txn_why: string | null;
  outcome: Outcome | null;
  outcome_label: string | null;
  primary_code: string | null;
  why: string | null;
  owner: string | null;
  next_step: string | null;
  also: string[];
  agent_note: string | null;
  decided_at: string | null;
  is_seed: number;
}

export interface Line {
  description: string;
  hsn_sac: string | null;
  qty: string;
  unit: string | null;
  rate: string;
  taxable: string;
  gst_rate: string | null;
}

export interface Invoice {
  supplier_name: string | null;
  supplier_gstin: string | null;
  invoice_no: string | null;
  invoice_date: string | null;
  po_ref: string | null;
  lines: Line[];
  taxable_total: string | null;
  grand_total: string | null;
  confidence: Record<string, number>;
  [key: string]: unknown;
}

export interface CaseDetail extends CaseSummary, CaseDetailExtras {
  invoice: Invoice | null;
  findings: Finding[];
  tool_calls: { node: string; tool: string; args: unknown; result: unknown; at: string }[];
  llm_calls: { node: string; model: string; reasoning: string | null; latency_ms: number; at: string }[];
  human_actions: { action: string; actor: string; note: string | null; at: string }[];
  file: string | null;
  pages: string[];
}

export interface CaseEvent {
  type: string;
  seq: number;
  payload: Record<string, unknown>;
}

export interface Sample {
  id: string;
  title: string;
  blurb: string;
  layout: string;
  scanned: boolean;
  vendor: string;
  total: string;
  expected_outcome: Outcome;
  expected_code: string;
}

export interface Kpis {
  days?: number | null;
  processed: number;
  total_inr: string;
  touchless: number;
  touchless_pct: number;
  exceptions: number;
  protected_inr: string;
  protected_cases: number;
  avg_handling_seconds: number | null;
  outcomes: Record<"approved" | "needs_signoff" | "on_hold" | "rejected", number>;
  by_type: Record<TxnType, number>;
  touchless_series: { date: string; cases: number; touchless_pct: number | null }[];
}

export type Pace = "fast" | "normal" | "presenter";

export interface ActionBody {
  action: "approve_anyway" | "sign_off" | "reject" | "ask_vendor" | "confirm_field" | "recheck";
  note?: string;
  field?: string;
  value?: string;
  actor?: string;
  action_key: string;
}

export interface CaseDetailExtras {
  locked_codes: string[];
}

export interface TrailStep {
  kind: "contract" | "po" | "grn" | "earlier" | "invoice" | "check" | "decision" | "person";
  date: string | null;
  who: string;
  title: string;
  detail: string;
  case_id?: string;
}

export interface TrailPoLine {
  line_no: number; item_code: string; description: string; hsn_sac: string; qty: string; unit: string; rate: string;
  gst_rate: string; amount: string; received_qty: string | null; received_date: string | null;
  billed_before_qty: string; billed_before_amount: string;
}

export interface Trail {
  vendor: { vendor_id: string; name: string; gstin: string; category: string; bank: string; payment_terms_days: number; status: string } | null;
  po: { po_number: string; po_date: string; po_type: string; status: string; value: string; lines: TrailPoLine[] } | null;
  grns: { grn_number: string; po_number: string; line_no: number; received_qty: string; accepted_qty: string; received_date: string }[];
  contract: { contract_id: string; start_date: string; end_date: string; billing_cycle: string; amount_per_period: string; description: string } | null;
  earlier_invoices: { case_id: string; invoice_no: string | null; invoice_date: string | null; amount: string; outcome: string | null }[];
  invoice: { invoice_no: string | null; invoice_date: string | null; grand_total: string | null; lines: Line[] } | null;
  steps: TrailStep[];
}
