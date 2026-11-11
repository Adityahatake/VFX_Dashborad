import { useState } from "react";
import { api } from "../api";
import { useFetch } from "../hooks";
import { Alert, Badge, Button, Card, cx, inputCls, Stat, statusTone } from "../ui";
import { LogView } from "./LogView";

type Dry = { rows: number; add: number; skipped: { company: string; name: string; why: string }[]; warnings: string[]; stop: string | null; current: boolean; label?: string };
type SheetState = {
  target: string; targets: Record<string, string>; demo: boolean; read_only: boolean; batch_size: number; write_tab: string; cycle: number | null;
  goal_rows?: number; baseline?: { data_rows: number; taken_at: string; last_row_name: string } | null; approved?: number; appended?: number;
  csv?: { rows: number; header: string[]; preview: Record<string, string>[] } | null; dry_run?: Dry | null;
  recovery?: { reason: string; has_file: boolean } | null; append_job?: { id: number; status: string; error: string | null } | null;
  progress?: { baseline: number; ours: number; current: number; added_by_others: number }; label?: string;
};

/** Show before write: build the review CSV, dry-run it against the live sheet, type the row count, append (a gated, never-retried job). */
export function SheetAppend({ tick, onChanged }: { tick: number; onChanged: () => void }) {
  const [withProgress, setWithProgress] = useState(false);
  const { data: s, reload, error, loading } = useFetch<SheetState>(`/api/sheet${withProgress ? "?progress=1" : ""}`, [tick, withProgress]);
  const [typed, setTyped] = useState("");
  const [word, setWord] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "good" | "bad" | "info"; text: string } | null>(null);
  const [showCsv, setShowCsv] = useState(false);

  const act = async (f: () => Promise<unknown>, ok?: (r: unknown) => string) => {
    setBusy(true); setMsg(null);
    try { const r = await f(); if (ok) setMsg({ tone: "good", text: ok(r) }); reload(); onChanged(); }
    catch (e) { setMsg({ tone: "bad", text: (e as Error).message }); } finally { setBusy(false); }
  };

  if (!s) return <Card title="Sheet & append">{error ? <Alert tone="bad">{error}</Alert> : <div className="text-sm text-muted">Loading…</div>}</Card>;
  const dry = s.dry_run;
  const job = s.append_job;
  const jobLive = job && (job.status === "running" || job.status === "queued");
  const canAppend = !!s.csv && !!dry && dry.current && !dry.stop && !s.read_only && !s.recovery && typed.trim() === String(s.csv.rows) && !jobLive;

  return (
    <Card title="Sheet & append" actions={s.cycle ? <a className="text-xs text-muted hover:text-text" href="/api/cycle/report" target="_blank" rel="noreferrer">Cycle report (Markdown)</a> : null}>
      {/* target */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted">Sheet target:</span>
        {s.demo ? <Badge tone="warn">Demo sheet (in memory)</Badge> : Object.entries(s.targets).map(([k, label]) => (
          <button key={k} disabled={busy} onClick={() => k === "real" ? setPending("real") : act(() => api.put("/api/sheet/target", { target: k }))}
            className={cx("rounded-lg border px-2.5 py-1 text-xs", s.target === k ? (k === "real" ? "border-bad text-bad" : "border-accent-2 text-accent-2") : "border-line text-muted hover:text-text")}>{label}</button>
        ))}
      </div>
      {pending === "real" && (
        <div className="mt-2 space-y-2 rounded-lg border border-bad/40 bg-bad/5 p-3 text-sm">
          <div>This allows writes to the <b>real shared sheet</b>. Type <span className="font-mono">REAL SHEET</span> to confirm.</div>
          <div className="flex gap-2"><span className="w-48"><input className={inputCls} value={word} onChange={(e) => setWord(e.target.value)} /></span>
            <Button kind="danger" disabled={word !== "REAL SHEET"} onClick={() => act(async () => { await api.put("/api/sheet/target", { target: "real", confirm: word }); setPending(null); setWord(""); })}>Switch</Button>
            <Button kind="ghost" onClick={() => { setPending(null); setWord(""); }}>Cancel</Button></div>
        </div>
      )}
      {!s.cycle ? <div className="mt-3"><Alert tone="info">Start a cycle to build and append rows.</Alert></div> : (
        <>
          {/* baseline */}
          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="Approved people" value={s.approved ?? 0} hint={`goal ${s.goal_rows}`} />
            <Stat label="Appended (ours)" value={s.appended ?? 0} />
            <Stat label="Baseline" value={s.baseline ? s.baseline.data_rows : "—"} hint={s.baseline ? `taken ${s.baseline.taken_at.slice(0, 16)}` : "not taken"} />
            <Stat label="On sheet now" value={s.progress ? s.progress.current : "—"} hint={s.progress ? `${s.progress.added_by_others} added by others` : withProgress && loading ? "reading the sheet…" : <button className="underline" onClick={() => setWithProgress(true)}>read the sheet</button>} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button disabled={busy || (!!s.baseline && (s.appended ?? 0) > 0)} onClick={() => act(() => api.post("/api/sheet/baseline"), () => "Baseline taken (read-only).")}>
              {s.baseline ? "Retake baseline" : "Take baseline"}</Button>
          </div>

          {s.recovery && (
            <div className="mt-3"><Alert tone="bad">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>A write ended with an unknown outcome ({s.recovery.reason}). Appending is blocked until recovery reads the sheet tail. It is never retried.</span>
                <Button kind="danger" disabled={busy || !s.recovery.has_file} onClick={() => act(() => api.post("/api/sheet/recover"),
                  (r) => { const x = r as { landed: number[]; missing: number; note: string }; return `${x.landed.length} row(s) had landed; ${x.missing} missing (rebuilt as the next CSV). ${x.note}`; })}>Run recovery</Button>
              </div>
            </Alert></div>
          )}

          {/* 1 build */}
          <div className="mt-4 text-sm font-medium">1. Build the review CSV</div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Button disabled={busy || !s.approved} onClick={() => act(() => api.post("/api/sheet/csv"), (r) => `Built review.csv with ${(r as { rows: number }).rows} row(s). Run the dry run next.`)}>Build CSV from approved people</Button>
            {s.csv && <button className="text-xs text-muted hover:text-text" onClick={() => setShowCsv(!showCsv)}>{showCsv ? "Hide" : "Show"} {s.csv.rows} row(s)</button>}
          </div>
          {showCsv && s.csv && (
            <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-line">
              <table className="text-xs"><thead className="bg-panel-2 text-left text-muted"><tr>{s.csv.header.map((h) => <th key={h} className="whitespace-nowrap px-2 py-1">{h}</th>)}</tr></thead>
                <tbody>{s.csv.preview.map((r, i) => <tr key={i} className="border-t border-line">{s.csv!.header.map((h) => <td key={h} className="max-w-56 truncate px-2 py-1" title={r[h]}>{r[h]}</td>)}</tr>)}</tbody></table>
            </div>
          )}

          {/* 2 dry run */}
          <div className="mt-4 text-sm font-medium">2. Dry run <span className="font-normal text-muted">(reads the sheet, writes nothing)</span></div>
          <div className="mt-1"><Button disabled={busy || !s.csv} onClick={() => act(() => api.post("/api/sheet/dry-run"))}>Dry-run append</Button></div>
          {dry && (
            <div className="mt-2 space-y-1.5">
              {!dry.current && <Alert tone="warn">The CSV changed since this dry run: run it again.</Alert>}
              {dry.stop ? <Alert tone="bad">Would stop: {dry.stop}</Alert> : <Alert tone="good">Would add {dry.add} of {dry.rows} row(s){dry.label ? ` to ${dry.label}` : ""}.</Alert>}
              {dry.skipped.length > 0 && <ul className="list-inside list-disc text-xs text-muted">{dry.skipped.map((x, i) => <li key={i}>skip <b className="text-text">{x.name}</b> ({x.company}): {x.why}</li>)}</ul>}
              {dry.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
            </div>
          )}

          {/* 3 append */}
          <div className="mt-4 text-sm font-medium">3. Append</div>
          <p className="mt-1 text-xs text-muted">Batches of {s.batch_size}; the tabs are re-read before every batch; nothing is ever retried, deleted or reordered; only our own rows are recoloured.</p>
          {s.read_only && <div className="mt-2"><Alert tone="info">The target is read-only: the dry run is as far as this goes. Choose the sandbox or the real sheet (with writes) to append.</Alert></div>}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="w-56"><input className={inputCls} placeholder={s.csv ? `type ${s.csv.rows} to confirm` : "build the CSV first"} value={typed} onChange={(e) => setTyped(e.target.value)} disabled={!s.csv} /></span>
            <Button kind="primary" disabled={busy || !canAppend} onClick={() => act(async () => { await api.post("/api/sheet/append", { typed_rows: Number(typed) }); setTyped(""); }, () => "Append started. Follow it below.")}>Append to sheet</Button>
          </div>
          {job && (
            <div className="mt-3 rounded-lg border border-line bg-panel-2 p-3 text-sm">
              Last append: job #{job.id} <Badge tone={statusTone(job.status)}>{job.status}</Badge>
              {job.error && <div className="mt-2"><Alert tone="bad">{job.error}</Alert></div>}
              <LogView jobId={job.id} live={!!jobLive} />
            </div>
          )}
        </>
      )}
      {msg && <div className="mt-3"><Alert tone={msg.tone}>{msg.text}</Alert></div>}
    </Card>
  );
}
