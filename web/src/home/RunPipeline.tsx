import { useEffect, useState } from "react";
import { api, type GateView, type Job, type Progress as Prog } from "../api";
import { Alert, Badge, Button, Card, cx, Field, inputCls, Progress, Stat, statusTone, usd } from "../ui";
import { LogView } from "./LogView";

type Params = { tavily_queries: number; crawl_limit: number; leads_max_result: number; min_evidence_score: number; time_range: string; pool_match: boolean };
const DEFAULTS: Params = { tavily_queries: 20, crawl_limit: 60, leads_max_result: 50, min_evidence_score: 2, time_range: "month", pool_match: true };

/** Run Pipeline: choose the size, see the maximum cost and anything blocking it, confirm once, run. */
export function RunPipeline({ hasCycle, live, onStarted }: { hasCycle: boolean; live: boolean; onStarted: () => void }) {
  const [p, setP] = useState<Params>(DEFAULTS);
  const [gate, setGate] = useState<GateView | null>(null);
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => { setGate(null); setOk(false); }, [p]);
  const set = (k: keyof Params, v: number | string | boolean) => setP({ ...p, [k]: v });

  const check = async () => {
    setBusy(true); setErr(null);
    try { setGate(await api.post<GateView>("/api/steps/vfx_pipeline/gate", { params: p })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const run = async () => {
    if (!gate) return;
    setBusy(true); setErr(null);
    try {
      await api.post("/api/pipeline/run", { params: p, confirmed_max_usd: gate.estimate.max_usd });
      setGate(null); setOk(false); onStarted();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <Card title="Run pipeline" actions={<Button kind="ghost" onClick={() => setOpen(!open)}>{open ? "Hide settings" : "Settings"}</Button>}>
      <p className="text-sm text-muted">
        Finds VFX and production studios using generative AI in client work (Tavily), checks their own sites for evidence, finds the
        decision-makers (Apify) and validates them against the sheet. Results wait for your review. Nothing is written to the sheet.
      </p>
      {open && (
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">
          <Field label="Tavily searches" hint="1 credit each"><input type="number" min={1} max={200} className={inputCls} value={p.tavily_queries} onChange={(e) => set("tavily_queries", +e.target.value)} /></Field>
          <Field label="Sites to crawl (max)" hint="free"><input type="number" min={1} max={5000} className={inputCls} value={p.crawl_limit} onChange={(e) => set("crawl_limit", +e.target.value)} /></Field>
          <Field label="People results (max)" hint="Apify, ~$0.003 each"><input type="number" min={1} max={500} className={inputCls} value={p.leads_max_result} onChange={(e) => set("leads_max_result", +e.target.value)} /></Field>
          <Field label="Evidence needed for auto-pass" hint="sentences on the company's own site"><input type="number" min={1} max={20} className={inputCls} value={p.min_evidence_score} onChange={(e) => set("min_evidence_score", +e.target.value)} /></Field>
          <Field label="Search recency">
            <select className={inputCls} value={p.time_range} onChange={(e) => set("time_range", e.target.value)}>
              {["day", "week", "month", "year"].map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Free pool matching"><label className="flex items-center gap-2 pt-1.5 text-sm"><input type="checkbox" checked={p.pool_match} onChange={(e) => set("pool_match", e.target.checked)} /> 2nd/3rd contacts from paid pools</label></Field>
        </div>
      )}
      {!hasCycle && <div className="mt-3"><Alert tone="info">Start a cycle first: it sets the goal and the spend cap.</Alert></div>}
      {gate && (
        <div className="mt-3 space-y-2 rounded-lg border border-line bg-panel-2 p-3">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            <Stat label="Maximum cost" value={usd(gate.estimate.max_usd)} hint={gate.estimate.note} />
            <Stat label="Cycle cap left" value={usd(gate.remaining)} hint={`worst case after: ${usd(gate.remaining - gate.estimate.max_usd)}`} />
            <Stat label="Status" value={gate.ok ? "Ready" : "Blocked"} tone={gate.ok ? "good" : "bad"} />
          </div>
          {gate.blockers.map((b) => <Alert key={b} tone="bad">{b}</Alert>)}
          {gate.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
          {(gate.exhausted ?? []).map((x) => <Alert key={x.source} tone="warn">Exhausted source: {x.source}. {x.note}</Alert>)}
          {gate.ok && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
              I confirm this run may spend up to <b>{usd(gate.estimate.max_usd)}</b> (it stops earlier if a stop rule trips).
            </label>
          )}
        </div>
      )}
      {err && <div className="mt-2"><Alert tone="bad">{err}</Alert></div>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={check} disabled={busy || live || !hasCycle}>Check cost and readiness</Button>
        <Button kind="primary" onClick={run} disabled={busy || live || !gate?.ok || !ok}>▶ Run pipeline</Button>
        {live && <span className="self-center text-xs text-muted">A run is in progress.</span>}
      </div>
    </Card>
  );
}

const COUNT_LABELS: [string, string][] = [
  ["companies_found", "Companies found"], ["companies_crawled", "Sites crawled"], ["companies_qualified", "Companies qualified"],
  ["people_found", "People found"], ["people_valid", "People saved"], ["records_skipped", "Records skipped"],
];

/** Live progress of the latest pipeline run: stages, current task, counts, API spend, errors, and the technical log on demand. */
export function LiveRun({ job, progress, onChanged }: { job: Job | null; progress: Prog | null; onChanged: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const [resumeGate, setResumeGate] = useState<GateView | null>(null);
  if (!job) return null;
  const running = job.status === "running" || job.status === "queued";
  const stages = progress?.stages ?? [];
  const idx = progress?.stage_index ?? 0;
  const c = progress?.counts ?? {};
  const resumable = ["interrupted", "failed", "cancelled"].includes(job.status);

  const cancel = async () => { try { await api.post(`/api/jobs/${job.id}/cancel`); onChanged(); } catch (e) { setErr((e as Error).message); } };
  const prepResume = async () => { try { setResumeGate(await api.get<GateView>(`/api/jobs/${job.id}/resume-gate`)); } catch (e) { setErr((e as Error).message); } };
  const resume = async () => {
    if (!resumeGate) return;
    try { await api.post(`/api/jobs/${job.id}/resume`, { confirmed_max_usd: resumeGate.estimate.max_usd, confirmed_key_id: resumeGate.key_id }); setResumeGate(null); onChanged(); }
    catch (e) { setErr((e as Error).message); }
  };

  return (
    <Card title={<span className="flex items-center gap-2">Pipeline run #{job.id} <Badge tone={statusTone(job.status)}>{job.status}</Badge></span>}
      actions={running ? <Button kind="danger" onClick={cancel} disabled={!!job.cancel_requested}>{job.cancel_requested ? "Stopping…" : "Cancel"}</Button>
        : resumable ? <Button onClick={prepResume}>Resume…</Button> : null}>
      <div className="flex items-center gap-3">
        <div className="flex-1"><Progress value={progress?.percent ?? 0} /></div>
        <span className="w-14 text-right text-sm tabular-nums text-muted">{(progress?.percent ?? 0).toFixed(0)}%</span>
      </div>
      <div className="mt-2 text-sm">
        <span className="font-medium">{progress?.stage ?? "Starting…"}</span>
        {progress?.step && <span className="text-muted"> · {progress.step}</span>}
      </div>
      {running && job.last_line && <div className="mt-1 truncate font-mono text-xs text-muted">{job.last_line}</div>}

      <ol className="mt-3 grid grid-cols-2 gap-1.5 md:grid-cols-4">
        {stages.map((s, i) => {
          const state = job.status === "done" || i < idx ? "done" : i === idx ? (running ? "now" : job.status === "done" ? "done" : "stopped") : "todo";
          return (
            <li key={s} className={cx("flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs",
              state === "done" && "border-good/30 text-good", state === "now" && "border-accent-2/50 text-accent-2", state === "stopped" && "border-warn/40 text-warn",
              state === "todo" && "border-line text-muted")}>
              <span className="w-4 text-center">{state === "done" ? "✓" : state === "now" ? "●" : state === "stopped" ? "!" : i + 1}</span>{s}
            </li>
          );
        })}
      </ol>

      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-6">
        {COUNT_LABELS.map(([k, l]) => <Stat key={k} label={l} value={typeof c[k] === "number" ? (c[k] as number) : "—"} />)}
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
        <span>Spend this run: <b className="text-text">{usd(progress?.api?.total_usd ?? 0)}</b> of {usd(progress?.budget_usd)}</span>
        <span>· Tavily {usd(progress?.api?.tavily_usd ?? 0)}</span>
        <span>· Apify {usd(progress?.api?.apify_usd ?? 0)}</span>
        {typeof c.tavily_searches === "number" && <span>· {c.tavily_searches as number} searches</span>}
      </div>

      {(progress?.errors ?? []).map((e, i) => <div key={"e" + i} className="mt-2"><Alert tone="bad">{e}</Alert></div>)}
      {job.error && !(progress?.errors ?? []).some((e) => job.error?.includes(e)) && <div className="mt-2"><Alert tone="bad">{job.error}</Alert></div>}
      {(progress?.warnings ?? []).map((w, i) => <div key={"w" + i} className="mt-2"><Alert tone="warn">{w}</Alert></div>)}
      {resumeGate && (
        <div className="mt-3 space-y-2 rounded-lg border border-line bg-panel-2 p-3 text-sm">
          <div>Resume re-checks the cap, keys and stop rules. Maximum cost: <b>{usd(resumeGate.estimate.max_usd)}</b>; cycle cap left {usd(resumeGate.remaining)}.</div>
          {resumeGate.blockers.map((b) => <Alert key={b} tone="bad">{b}</Alert>)}
          <div className="flex gap-2"><Button kind="primary" disabled={!resumeGate.ok} onClick={resume}>Confirm and resume</Button><Button kind="ghost" onClick={() => setResumeGate(null)}>Cancel</Button></div>
        </div>
      )}
      {err && <div className="mt-2"><Alert tone="bad">{err}</Alert></div>}
      <LogView jobId={job.id} live={running} />
    </Card>
  );
}
