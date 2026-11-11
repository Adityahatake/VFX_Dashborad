import { useEffect, useMemo, useState } from "react";
import type { CycleInfo, Health, KeysInfo, PipelineRun } from "../api";
import { useFetch, useLive } from "../hooks";
import { CycleCard } from "./CycleCard";
import { HealthStrip } from "./HealthStrip";
import { Jobs, RecentRuns } from "./Jobs";
import { LatestCompanies, LatestPeople } from "./Review";
import { LiveRun, RunPipeline } from "./RunPipeline";
import { RunStep } from "./RunStep";
import { SheetAppend } from "./SheetAppend";

/** The control centre: start and watch the pipeline, manage jobs, review what it found. */
export function Home({ goKeys }: { goKeys: () => void }) {
  const { snap, connected } = useLive();
  // A change in jobs or spend (pushed live by the server) refreshes the lists that depend on them.
  const sig = useMemo(() => JSON.stringify([snap?.jobs.map((j) => [j.id, j.status]), snap?.cycle?.spent_usd, snap?.pipeline?.progress?.stage]), [snap]);
  const [tick, setTick] = useState(0);
  useEffect(() => setTick((t) => t + 1), [sig]);

  const health = useFetch<Health>("/api/health", [tick], 15000);
  const keys = useFetch<KeysInfo>("/api/keys", [], 30000);
  const cycle = useFetch<CycleInfo>("/api/cycle", [tick]);
  const runs = useFetch<PipelineRun[]>("/api/pipeline/runs?limit=8", [tick]);

  const pj = snap?.pipeline ?? null;
  const pjob = pj ? snap!.jobs.find((j) => j.id === pj.job_id) ?? null : null;
  const live = !!pjob && (pjob.status === "running" || pjob.status === "queued");
  const hasCycle = !!cycle.data?.active;
  const refresh = () => { setTick((t) => t + 1); cycle.reload(); runs.reload(); health.reload(); };

  return (
    <div className="space-y-4">
      <HealthStrip health={health.data} keys={keys.data} connected={connected} onKeys={goKeys} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="space-y-4">
          <CycleCard cycle={cycle.data} reload={refresh} spent={snap?.cycle?.spent_usd} />
          <RunPipeline hasCycle={hasCycle} live={live} onStarted={refresh} />
        </div>
        <div className="space-y-4">
          {pjob ? <LiveRun job={pjob} progress={pj?.progress ?? null} onChanged={refresh} />
            : <div className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">No pipeline run yet. Start a cycle, check the cost and press Run pipeline.</div>}
          <RecentRuns runs={runs.data ?? []} />
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <LatestCompanies tick={tick} onChanged={refresh} />
        <LatestPeople tick={tick} onChanged={refresh} />
      </div>
      <SheetAppend tick={tick} onChanged={refresh} />
      <Jobs jobs={snap?.jobs ?? []} onChanged={refresh} />
      <RunStep hasCycle={hasCycle} onStarted={refresh} />
    </div>
  );
}
