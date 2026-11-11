// Thin client for the FastAPI backend. Every safety rule lives on the server; this only calls it and shows the answer.

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : describe(detail));
    this.status = status;
    this.detail = detail;
  }
}

function describe(d: unknown): string {
  if (d && typeof d === "object") {
    const o = d as Record<string, unknown>;
    if (Array.isArray(o.blockers)) return (o.blockers as string[]).join("; ");
    if (Array.isArray(o.problems)) return (o.problems as string[]).join("; ");
  }
  return JSON.stringify(d);
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await r.text();
  const data = text ? JSON.parse(text) : null;
  if (!r.ok) throw new ApiError(r.status, data?.detail ?? data ?? r.statusText);
  return data as T;
}

export const api = {
  get: <T,>(p: string) => call<T>("GET", p),
  post: <T,>(p: string, b: unknown = {}) => call<T>("POST", p, b),
  put: <T,>(p: string, b: unknown) => call<T>("PUT", p, b),
  del: <T,>(p: string) => call<T>("DELETE", p),
};

// ---------------------------------------------------------------- types (mirror api/main.py)
export type Job = {
  id: number; cycle_id: number | null; step_id: string; status: string; kind: string | null; key_id: string | null;
  est_max_usd: number; started_at: string | null; finished_at: string | null; heartbeat_at: string | null; error: string | null;
  stuck: boolean; heartbeat_age_s: number | null; params: Record<string, unknown>; resumed_count: number; cancel_requested: number;
  last_line?: string;
};

export type Progress = {
  stages: string[]; stage_index: number; stage: string; step: string; percent: number; budget_usd: number;
  counts: Record<string, number | boolean>; api: Record<string, number>; errors: string[]; warnings: string[];
};

export type Snapshot = {
  jobs: Job[];
  cycle: { id: number; spent_usd: number; cap_usd: number } | null;
  pipeline: { job_id: number; progress: Progress | null } | null;
};

export type StopEvent = { id: number; rule: string; reason: string; tripped_at: string };

export type CycleInfo = {
  active: { id: number; goal_rows: number; cap_usd: number; started_at: string; baseline_json: string | null } | null;
  spent_usd?: number; remaining_usd?: number; rows_approved?: number; rows_appended?: number;
  stop_events?: StopEvent[]; default_cap_usd?: number; hard_max_cap_usd: number;
};

export type Health = {
  pipeline: string; demo: boolean; sheet_target: string; running_jobs: number; stuck_jobs: number[]; interrupted_jobs: number;
  pending_review: { companies: number; people: number };
};

export type Warning = { provider: string; level: "info" | "warning" | "error"; message: string; keys?: string[] };
export type KeyRow = { key_prefix: string; provider: string; state: string; remaining: number | null; cap: number | null; resets: string; checked_at: string | null; in_use: boolean };
export type Provider = {
  label: string; unit: string; env_var: string; prefix: string; configured: number; usable: number; dead: number;
  total_remaining: number | null; keys: KeyRow[]; warnings: Warning[];
  usage: { calls: number; spent_usd: number; spent_30d_usd: number; results: number; last_used: string | null };
};
export type KeysInfo = { providers: Record<string, Provider>; low_credit_threshold: number; usable_apify_credit: number; demo: boolean };

export type GateView = {
  step_id: string; kind: string; ok: boolean; estimate: { max_usd: number; provider: string; key_required: boolean; note: string };
  key_id: string | null; key_balance: number | null; cycle_cap: number; cycle_spent: number; remaining: number;
  blockers: string[]; warnings: string[]; exhausted?: { source: string; note: string; date: string }[];
};

export type Step = { id: string; kind: string; title: string; stage: string | null; default_params: Record<string, unknown>; in_pipeline: boolean };

export type Company = {
  id: number; cycle_id: number; domain: string; name: string; country: string; source: string; decision: string;
  reason_code: string | null; decided_at: string | null; score: number | null; evidence: [string, string][];
};

export type Person = {
  id: number; cycle_id: number; domain: string; confidence: string; decision: string; reason_code: string | null;
  decided_at: string | null; fields: Record<string, string>; flags: string[]; problems: string[];
};

export type PipelineRun = {
  job_id: number; cycle_id: number; status: string; stage: string; started_at: string; finished_at: string | null;
  budget_usd: number; spent_usd: number; counts: Record<string, number>; errors: string[]; job_status: string; error: string | null;
};

export type PipelineState = { stages: string[]; defaults: Record<string, unknown>; live_job: Job | null; last_job: Job | null; progress: Progress | null };
