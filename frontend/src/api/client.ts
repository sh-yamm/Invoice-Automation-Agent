import type { ActionBody, CaseDetail, CaseEvent, CaseSummary, Kpis, Pace, Sample, Trail } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listCases = (filters: Record<string, string | number | undefined> = {}) => {
  const q = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)]),
  );
  return call<CaseSummary[]>(`/api/cases${q.toString() ? `?${q}` : ""}`);
};

export const getCase = (id: string) => call<CaseDetail>(`/api/cases/${id}`);

export const createCase = (input: { sampleId?: string; file?: File; pace?: Pace }) => {
  const form = new FormData();
  if (input.sampleId) form.append("sample_id", input.sampleId);
  if (input.file) form.append("file", input.file);
  form.append("pace", input.pace ?? "normal");
  return call<{ case_id: string }>("/api/cases", { method: "POST", body: form });
};

export function streamEvents(id: string, onEvent: (e: CaseEvent) => void, onEnd?: () => void): () => void {
  const es = new EventSource(`/api/cases/${id}/events`);
  const types = ["node_started", "node_finished", "finding", "decision", "human_action", "finalised"];
  for (const t of types) {
    es.addEventListener(t, (m) => {
      const msg = m as MessageEvent;
      onEvent({ type: t, seq: Number(msg.lastEventId), payload: JSON.parse(msg.data) });
    });
  }
  es.addEventListener("end", () => {
    es.close();
    onEnd?.();
  });
  es.onerror = () => {
    es.close();
    onEnd?.();
  };
  return () => es.close();
}

export const sendAction = (id: string, body: ActionBody) => call<CaseDetail>(`/api/cases/${id}/actions`, json(body));
export const getAop = () => call<Record<string, any>>("/api/aop");
export const putAop = (changes: Record<string, unknown>, editor: string, why: string) =>
  call<Record<string, any>>("/api/aop", json({ changes, editor, why }, "PUT"));
export const getData = (name: string) => call<Record<string, any>[]>(`/api/data/${name}`);
export const getKpis = (days?: number) => call<Kpis>(`/api/kpis${days ? `?days=${days}` : ""}`);
export const getTrail = (id: string) => call<Trail>(`/api/cases/${id}/trail`);
export const getSamples = () => call<Sample[]>("/api/samples");
export const resetDemo = () => call<{ cases: number }>("/api/demo/reset", { method: "POST" });
