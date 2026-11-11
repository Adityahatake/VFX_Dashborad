import { useEffect, useMemo, useState } from "react";
import { api, type GateView, type Step } from "../api";
import { useFetch } from "../hooks";
import { Alert, Badge, Button, Card, cx, inputCls, Stat, usd } from "../ui";
import { stepName } from "./Jobs";

/** Run Cycle (advanced): run one step of the pipeline by itself, with the same cost gate as the full run. */
export function RunStep({ hasCycle, onStarted }: { hasCycle: boolean; onStarted: () => void }) {
  const { data: steps } = useFetch<Step[]>("/api/steps");
  const list = useMemo(() => (steps ?? []).filter((s) => s.id !== "vfx_pipeline" && s.id !== "append_sheet"), [steps]);
  const [sid, setSid] = useState("");
  const step = list.find((s) => s.id === sid) ?? list[0];
  const [raw, setRaw] = useState("{}");
  const [gate, setGate] = useState<GateView | null>(null);
  const [ok, setOk] = useState(false);
  const [msg, setMsg] = useState<{ tone: "bad" | "good"; text: string } | null>(null);

  useEffect(() => { if (step) { setRaw(JSON.stringify(step.default_params, null, 2)); setGate(null); setOk(false); } }, [step?.id]);  // eslint-disable-line react-hooks/exhaustive-deps

  const params = () => { try { return JSON.parse(raw || "{}"); } catch { throw new Error("Parameters are not valid JSON"); } };
  const check = async () => {
    setMsg(null); setOk(false);
    try { setGate(await api.post<GateView>(`/api/steps/${step!.id}/gate`, { params: params() })); } catch (e) { setMsg({ tone: "bad", text: (e as Error).message }); }
  };
  const run = async () => {
    setMsg(null);
    try {
      const body = step!.kind === "free" ? { step_id: step!.id, params: params() }
        : { step_id: step!.id, params: params(), confirmed_max_usd: gate!.estimate.max_usd, confirmed_key_id: gate!.key_id };
      const r = await api.post<{ job_id: number }>("/api/jobs", body);
      setMsg({ tone: "good", text: `Started job #${r.job_id}. Follow it in Jobs.` }); setGate(null); setOk(false); onStarted();
    } catch (e) { setMsg({ tone: "bad", text: (e as Error).message }); }
  };

  if (!step) return null;
  const free = step.kind === "free";
  return (
    <Card title="Run cycle step (advanced)">
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="space-y-2">
          <select className={inputCls} value={step.id} onChange={(e) => setSid(e.target.value)}>
            {list.map((s) => <option key={s.id} value={s.id}>{stepName(s.id)} · {s.kind}</option>)}
          </select>
          <div className="flex items-center gap-2 text-xs text-muted"><Badge tone={free ? "good" : "accent"}>{step.kind}</Badge>{step.title}</div>
          {!free && !hasCycle && <Alert tone="info">Paid steps need an active cycle.</Alert>}
        </div>
        <textarea className={cx(inputCls, "h-32 font-mono text-xs")} value={raw} onChange={(e) => { setRaw(e.target.value); setGate(null); setOk(false); }} spellCheck={false} />
      </div>
      {gate && !free && (
        <div className="mt-3 space-y-2 rounded-lg border border-line bg-panel-2 p-3">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Maximum cost" value={usd(gate.estimate.max_usd)} hint={gate.estimate.note} />
            <Stat label="Key" value={gate.key_id ? gate.key_id + "…" : "none"} hint={gate.key_balance != null ? `balance $${gate.key_balance.toFixed(2)}` : undefined} />
            <Stat label="Cycle cap left" value={usd(gate.remaining)} />
          </div>
          {gate.blockers.map((b) => <Alert key={b} tone="bad">{b}</Alert>)}
          {gate.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
          {gate.ok && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> I confirm a maximum cost of <b>{usd(gate.estimate.max_usd)}</b></label>}
        </div>
      )}
      {gate && free && gate.exhausted?.map((x) => <div key={x.source} className="mt-2"><Alert tone="warn">Exhausted source: {x.source}. {x.note}</Alert></div>)}
      {msg && <div className="mt-2"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
      <div className="mt-3 flex gap-2">
        {free ? <><Button onClick={check}>Check</Button><Button kind="primary" onClick={run}>Run (free)</Button></>
          : <><Button onClick={check} disabled={!hasCycle}>Check cost</Button><Button kind="primary" disabled={!gate?.ok || !ok} onClick={run}>Run {step.kind} step</Button></>}
      </div>
    </Card>
  );
}
