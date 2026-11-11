import { useState } from "react";
import { api, type CycleInfo } from "../api";
import { Alert, Button, Card, Field, inputCls, Stat, usd } from "../ui";

/** A cycle = one push toward a row goal with a spend cap. Paid work needs an active cycle. */
export function CycleCard({ cycle, reload, spent }: { cycle: CycleInfo | null; reload: () => void; spent?: number }) {
  const [goal, setGoal] = useState(100);
  const [cap, setCap] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  if (!cycle) return <Card title="Cycle"><div className="text-sm text-muted">Loading…</div></Card>;
  const a = cycle.active;

  const act = async (f: () => Promise<unknown>) => {
    setBusy(true); setErr(null);
    try { await f(); reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  if (!a) {
    const max = cycle.hard_max_cap_usd;
    const c = cap ?? cycle.default_cap_usd ?? max;
    return (
      <Card title="Start a cycle">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Goal (rows for the sheet)"><input type="number" min={1} max={1000} className={inputCls} value={goal} onChange={(e) => setGoal(+e.target.value)} /></Field>
          <Field label={`Spend cap (max $${max.toFixed(2)})`}><input type="number" min={0.05} step={0.25} max={max} className={inputCls} value={c} onChange={(e) => setCap(+e.target.value)} /></Field>
        </div>
        {c > max && <div className="mt-2"><Alert tone="warn">The cap will be limited to ${max.toFixed(2)}.</Alert></div>}
        {err && <div className="mt-2"><Alert tone="bad">{err}</Alert></div>}
        <div className="mt-3"><Button kind="primary" disabled={busy || goal < 1} onClick={() => act(() => api.post("/api/cycle", { goal_rows: goal, cap_usd: c }))}>Start cycle</Button></div>
      </Card>
    );
  }

  const s = spent ?? cycle.spent_usd ?? 0;
  return (
    <Card title={`Cycle #${a.id}`} actions={
      confirmEnd
        ? <><span className="text-xs text-muted">End this cycle?</span><Button kind="danger" disabled={busy} onClick={() => act(async () => { await api.post("/api/cycle/end"); setConfirmEnd(false); })}>End</Button><Button kind="ghost" onClick={() => setConfirmEnd(false)}>Keep</Button></>
        : <Button kind="ghost" onClick={() => setConfirmEnd(true)}>End cycle</Button>
    }>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Goal" value={a.goal_rows} hint="rows" />
        <Stat label="Approved" value={cycle.rows_approved ?? 0} hint={`${cycle.rows_appended ?? 0} appended`} />
        <Stat label="Spent" value={usd(s)} hint={`of ${usd(a.cap_usd, 2)} cap`} tone={s > a.cap_usd * 0.8 ? "warn" : undefined} />
        <Stat label="Remaining" value={usd(cycle.remaining_usd)} hint="after running jobs" />
      </div>
      {(cycle.stop_events ?? []).map((ev) => (
        <div key={ev.id} className="mt-3">
          <Alert tone="bad">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span><b>Stop rule “{ev.rule}”:</b> {ev.reason}. Paid stages are blocked until you acknowledge it.</span>
              {ev.rule !== "append_recovery" && <Button kind="danger" disabled={busy} onClick={() => act(() => api.post(`/api/stop-events/${ev.id}/ack`))}>Acknowledge</Button>}
            </div>
          </Alert>
        </div>
      ))}
      {err && <div className="mt-2"><Alert tone="bad">{err}</Alert></div>}
    </Card>
  );
}
