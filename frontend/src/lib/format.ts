// Indian-style money formatting (₹1,29,000.00) from exact decimal strings.

export function inr(value: string | number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  const neg = n < 0;
  const [whole, frac] = Math.abs(n).toFixed(decimals).split(".");
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return `${neg ? "-" : ""}₹${rest ? `${rest},${last3}` : last3}${decimals ? `.${frac}` : ""}`;
}

export function lakh(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
  return inr(n, 0);
}

export function ago(iso: string | null): string {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h`;
  return `${Math.floor(s / 86400)} d`;
}

export const OUTCOME = {
  0: { label: "Approved", tone: "approved", icon: "✓" },
  1: { label: "Needs sign-off", tone: "signoff", icon: "✎" },
  2: { label: "On hold", tone: "hold", icon: "!" },
  3: { label: "Rejected", tone: "reject", icon: "✕" },
} as const;

export const TXN = {
  standard_po: "Standard PO",
  recurring: "Recurring",
  po_less: "PO-less",
} as const;
