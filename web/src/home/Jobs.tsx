import { Fragment, useState } from "react";
import { api, type GateView, type Job, type PipelineRun } from "../api";
import { ago, Alert, Badge, Button, Card, Empty, statusTone, usd } from "../ui";
import { LogView } from "./LogView";

const STEP_NAMES: Record<string, string> = {
  vfx_pipeline: "Full pipeline", harvest_tavily_press: "Tavily company search", deep_crawl: "Evidence crawl", harvest_revenuebase: "RevenueBase lists",
  harvest_directory: "Directory pages", leads_finder: "People search (Apify)", pool_match: "Pool matching", salesnav: "Sales Navigator",
  sheet_snapshot: "Sheet snapshot", evidence: "Impressum / team pages", append_sheet: "Sheet append", llm_verdicts: "AI company suggestions",
  llm_person_drafts: "AI person drafts",
};
export const stepName = (s: string) => STEP_NAMES[s] ?? s;

/** Every job (pipeline runs and single steps): status, heartbeat, cancel, resume (paid jobs are re-checked by the gate), log. */
export function Jobs({ jobs, onChanged }: { jobs: Job[]; onChanged: () => void }) {
  const [sel, setSel] = useState<number | null>(null);
  const [gate, setGate] = useState<{ id: number; g: GateView } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const act = async (f: () => Promise<unknown>) => { setErr(null); try { await f(); onChanged(); } catch (e) { setErr((e as Error).message); } };

  const resume = (j: Job) => act(async () => {
    if (j.kind && ["paid", "llm", "write"].includes(j.kind)) {
      setGate({ id: j.id, g: await api.get<GateView>(`/api/jobs/${j.id}/resume-gate`) });
    } else {
      await api.post(`/api/jobs/${j.id}/resume`, {});
    }
  });

  return (
    <Card title="Jobs">
      {jobs.length === 0 ? <Empty>No jobs yet.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1.5 pr-3">#</th><th className="pr-3">Task</th><th className="pr-3">Status</th><th className="pr-3">Started</th><th className="pr-3">Max cost</th><th /></tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const live = j.status === "running" || j.status === "queued";
                const resumable = ["interrupted", "failed", "cancelled"].includes(j.status);
                return (
                  <Fragment key={j.id}>
                    <tr className="border-t border-line">
                      <td className="py-2 pr-3 tabular-nums text-muted">{j.id}</td>
                      <td className="pr-3">{stepName(j.step_id)}{j.key_id && <span className="ml-2 text-xs text-muted">{j.key_id}…</span>}</td>
                      <td className="pr-3"><Badge tone={statusTone(j.status)}>{j.status}{j.stuck ? " · no heartbeat" : ""}</Badge></td>
                      <td className="pr-3 text-muted">{ago(j.started_at)}</td>
                      <td className="pr-3 tabular-nums text-muted">{j.est_max_usd ? usd(j.est_max_usd) : "free"}</td>
                      <td className="whitespace-nowrap py-1 text-right">
                        {live && <Button kind="danger" disabled={!!j.cancel_requested} onClick={() => act(() => api.post(`/api/jobs/${j.id}/cancel`))}>{j.cancel_requested ? "Stopping…" : "Cancel"}</Button>}
                        {resumable && <Button onClick={() => resume(j)}>Resume</Button>}
                        <Button kind="ghost" onClick={() => setSel(sel === j.id ? null : j.id)}>{sel === j.id ? "Close" : "Details"}</Button>
                      </td>
                    </tr>
                    {gate?.id === j.id && (
                      <tr><td colSpan={6} className="pb-3">
                        <div className="space-y-2 rounded-lg border border-line bg-panel-2 p-3 text-sm">
                          <div>Resume re-checks the cap, key and stop rules: max {usd(gate.g.estimate.max_usd)}{gate.g.key_id ? ` on ${gate.g.key_id}…` : ""}, cycle cap left {usd(gate.g.remaining)}.</div>
                          {gate.g.blockers.map((b) => <Alert key={b} tone="bad">{b}</Alert>)}
                          <div className="flex gap-2">
                            <Button kind="primary" disabled={!gate.g.ok} onClick={() => act(async () => {
                              await api.post(`/api/jobs/${j.id}/resume`, { confirmed_max_usd: gate.g.estimate.max_usd, confirmed_key_id: gate.g.key_id }); setGate(null);
                            })}>Confirm and resume</Button>
                            <Button kind="ghost" onClick={() => setGate(null)}>Cancel</Button>
                          </div>
                        </div>
                      </td></tr>
                    )}
                    {sel === j.id && (
                      <tr><td colSpan={6} className="pb-3">
                        {j.error && <Alert tone="bad">{j.error}</Alert>}
                        <div className="mt-1 text-xs text-muted">Parameters: <code className="font-mono">{JSON.stringify(j.params)}</code></div>
                        <LogView jobId={j.id} live={live} />
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {err && <div className="mt-2"><Alert tone="bad">{err}</Alert></div>}
    </Card>
  );
}

/** Finished and running pipeline runs with their headline numbers. */
export function RecentRuns({ runs }: { runs: PipelineRun[] }) {
  return (
    <Card title="Recent pipeline runs">
      {runs.length === 0 ? <Empty>No pipeline runs yet.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1.5 pr-3">Run</th><th className="pr-3">Status</th><th className="pr-3">Companies</th><th className="pr-3">Qualified</th><th className="pr-3">People saved</th><th className="pr-3">Spent</th><th>Started</th></tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.job_id} className="border-t border-line">
                  <td className="py-2 pr-3 tabular-nums">#{r.job_id}</td>
                  <td className="pr-3"><Badge tone={statusTone(r.status)}>{r.status}</Badge>{r.errors.length > 0 && <span className="ml-1 text-xs text-bad" title={r.errors.join("\n")}>{r.errors.length} error(s)</span>}</td>
                  <td className="pr-3 tabular-nums">{r.counts.companies_found ?? 0}</td>
                  <td className="pr-3 tabular-nums">{r.counts.companies_qualified ?? 0}</td>
                  <td className="pr-3 tabular-nums">{r.counts.people_valid ?? 0}</td>
                  <td className="pr-3 tabular-nums">{usd(r.spent_usd)} <span className="text-muted">/ {usd(r.budget_usd)}</span></td>
                  <td className="text-muted">{ago(r.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
