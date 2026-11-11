import type React from "react";
import { useState } from "react";
import { api, type Company, type Person } from "../api";
import { useFetch } from "../hooks";
import { ago, Alert, Badge, Button, Card, cx, decode, Empty, inputCls, statusTone } from "../ui";

type Reasons = { company: Record<string, string>; person: Record<string, string> };
/** AI suggestions arrive as light markdown; show them as plain text, clearly labelled, never as a decision. */
function Suggestion({ text, action }: { text: string; action?: React.ReactNode }) {
  return (
    <div className="mt-2 rounded-lg border border-accent-2/30 bg-accent-2/5 p-2 text-xs text-muted">
      <div className="whitespace-pre-wrap">{text.replace(/\*\*/g, "").replace(/^_(.*)_$/gm, "$1")}</div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

const FILTERS: [string, string][] = [["pending,look", "To review"], ["approved", "Approved"], ["rejected", "Rejected"], ["", "All"]];

function Filter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex rounded-lg border border-line p-0.5 text-xs">
      {FILTERS.map(([v, l]) => (
        <button key={l} onClick={() => onChange(v)} className={cx("rounded-md px-2 py-1", value === v ? "bg-panel-2 text-text" : "text-muted hover:text-text")}>{l}</button>
      ))}
    </div>
  );
}

function RejectBox({ reasons, onReject }: { reasons: Record<string, string>; onReject: (code: string) => void }) {
  const [code, setCode] = useState("");
  return (
    <span className="inline-flex items-center gap-1">
      <select className={cx(inputCls, "w-44 py-1 text-xs")} value={code} onChange={(e) => setCode(e.target.value)}>
        <option value="">Reject reason…</option>
        {Object.entries(reasons).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
      <Button kind="danger" disabled={!code} onClick={() => onReject(code)}>Reject</Button>
    </span>
  );
}

/** Latest discovered companies with their evidence. Approving a company lets the people search look for its decision-makers. */
export function LatestCompanies({ tick, onChanged }: { tick: number; onChanged: () => void }) {
  const [filter, setFilter] = useState("pending,look");
  const { data, reload } = useFetch<Company[]>(`/api/companies?limit=40&decision=${filter}`, [tick]);
  const { data: reasons } = useFetch<Reasons>("/api/review/reasons");
  const [err, setErr] = useState<string | null>(null);
  const decide = async (id: number, decision: string, reason?: string) => {
    setErr(null);
    try { await api.post(`/api/companies/${id}/decision`, { decision, reason }); reload(); onChanged(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Card title="Latest companies" actions={<Filter value={filter} onChange={setFilter} />}>
      {err && <div className="mb-2"><Alert tone="bad">{err}</Alert></div>}
      {!data || data.length === 0 ? <Empty>No companies here.</Empty> : (
        <ul className="space-y-2">
          {data.map((c) => (
            <li key={c.id} className="rounded-lg border border-line bg-panel-2 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <a href={`https://${c.domain}`} target="_blank" rel="noreferrer" className="font-medium hover:text-accent-2">{c.name || c.domain}</a>
                <span className="text-xs text-muted">{c.domain}</span>
                <Badge tone={statusTone(c.decision)}>{c.decision}</Badge>
                {c.reason_code && <Badge tone={c.reason_code.startsWith("AUTO_PASS") ? "good" : c.reason_code.startsWith("AUTO_HOLD") ? "warn" : "neutral"}>{c.reason_code}</Badge>}
                {c.score != null && <span className="text-xs text-muted">evidence ×{c.score}</span>}
                <span className="ml-auto text-xs text-muted">{c.source} · {ago(c.decided_at)}</span>
              </div>
              {c.evidence.slice(0, 1).map(([u, s]) => (
                <div key={u} className="mt-2 text-xs text-muted">
                  <span className="line-clamp-2">“{decode(s).replace(/\s+/g, " ").trim()}”</span>
                  <a href={u} target="_blank" rel="noreferrer" className="text-accent-2 hover:underline">{u}</a>
                </div>
              ))}
              {c.suggestion && <Suggestion text={c.suggestion} />}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {c.decision !== "approved" && <Button onClick={() => decide(c.id, "approved")}>Approve</Button>}
                {c.decision !== "look" && <Button kind="ghost" onClick={() => decide(c.id, "look")}>Needs a look</Button>}
                {c.decision !== "rejected" && reasons && <RejectBox reasons={reasons.company} onReject={(r) => decide(c.id, "rejected", r)} />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

const MAIN_FIELDS = ["why_this_person", "primary_commercial_problem", "ai_evidence", "evidence_source"];

function PersonEditor({ p, columns, onSaved, onClose }: { p: Person; columns: string[]; onSaved: () => void; onClose: () => void }) {
  const [f, setF] = useState<Record<string, string>>(() => Object.fromEntries(columns.map((c) => [c, p.fields[c] ?? ""])));
  const [more, setMore] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    setErr(null);
    try { await api.put(`/api/people/${p.id}/fields`, { fields: f }); onSaved(); onClose(); } catch (e) { setErr((e as Error).message); }
  };
  const shown = more ? columns : MAIN_FIELDS.filter((c) => columns.includes(c));
  return (
    <div className="mt-2 space-y-2 rounded-lg border border-line bg-ink p-3">
      {shown.map((c) => (
        <label key={c} className="block">
          <span className="text-xs text-muted">{c}</span>
          <textarea rows={c === "why_this_person" || c === "primary_commercial_problem" || c === "ai_evidence" ? 2 : 1} className={cx(inputCls, "mt-1 font-normal")}
            value={f[c]} onChange={(e) => setF({ ...f, [c]: e.target.value })} />
        </label>
      ))}
      {err && <Alert tone="bad">{err}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button kind="primary" onClick={save}>Save (back to pending)</Button>
        <Button kind="ghost" onClick={() => setMore(!more)}>{more ? "Fewer fields" : "All fields"}</Button>
        <Button kind="ghost" onClick={onClose}>Close</Button>
      </div>
    </div>
  );
}

/** Latest discovered people. A row can be approved only when it is complete (you write why_this_person yourself). */
export function LatestPeople({ tick, onChanged }: { tick: number; onChanged: () => void }) {
  const [filter, setFilter] = useState("pending,look");
  const { data, reload } = useFetch<Person[]>(`/api/people?limit=40&decision=${filter}`, [tick]);
  const { data: reasons } = useFetch<Reasons>("/api/review/reasons");
  const { data: columns } = useFetch<string[]>("/api/people/columns");
  const [edit, setEdit] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const decide = async (id: number, decision: string, reason?: string) => {
    setErr(null);
    try { await api.post(`/api/people/${id}/decision`, { decision, reason }); reload(); onChanged(); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <Card title="Latest people" actions={<Filter value={filter} onChange={setFilter} />}>
      {err && <div className="mb-2"><Alert tone="bad">{err}</Alert></div>}
      {!data || data.length === 0 ? <Empty>No people here.</Empty> : (
        <ul className="space-y-2">
          {data.map((p) => (
            <li key={p.id} className="rounded-lg border border-line bg-panel-2 p-3">
              <div className="flex flex-wrap items-center gap-2">
                {p.fields.contact_or_reference
                  ? <a href={p.fields.contact_or_reference} target="_blank" rel="noreferrer" className="font-medium hover:text-accent-2">{p.fields.name || "(no name)"}</a>
                  : <span className="font-medium">{p.fields.name || "(no name)"}</span>}
                <span className="text-xs text-muted">{p.fields.title} · {p.fields.company} · {p.fields.country || "country?"}</span>
                <Badge tone={statusTone(p.decision)}>{p.decision}</Badge>
                {p.confidence && <Badge tone={p.confidence === "High" ? "good" : "warn"}>{p.confidence}</Badge>}
                {p.reason_code && <Badge>{p.reason_code}</Badge>}
              </div>
              {p.problems.length > 0 && p.decision !== "rejected" && (
                <ul className="mt-2 list-inside list-disc text-xs text-warn">{p.problems.map((x) => <li key={x}>{x}</li>)}</ul>
              )}
              {p.suggestion && p.decision !== "approved" && (
                <Suggestion text={p.suggestion} action={<Button onClick={async () => {
                  setErr(null);
                  try { await api.post(`/api/people/${p.id}/use-suggestion`); reload(); onChanged(); } catch (e) { setErr((e as Error).message); }
                }}>Use this suggestion (you still approve)</Button>} />
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button onClick={() => setEdit(edit === p.id ? null : p.id)}>Edit fields</Button>
                {p.decision !== "approved" && (
                  <Button kind="primary" disabled={p.problems.length > 0} title={p.problems.length ? "Complete the fields first" : undefined}
                    onClick={() => decide(p.id, "approved")}>Approve</Button>
                )}
                {p.decision !== "rejected" && reasons && <RejectBox reasons={reasons.person} onReject={(r) => decide(p.id, "rejected", r)} />}
              </div>
              {edit === p.id && columns && <PersonEditor p={p} columns={columns} onSaved={() => { reload(); onChanged(); }} onClose={() => setEdit(null)} />}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
