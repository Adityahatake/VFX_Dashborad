import { useState } from "react";
import { api, type KeyRow, type KeysInfo, type Provider } from "../api";
import { useFetch } from "../hooks";
import { ago, Alert, Badge, Button, Card, cx, inputCls, Stat, statusTone, usd } from "../ui";

const ABOUT: Record<string, string> = {
  apify: "Finds the decision-makers at qualified studios (people search). Balance is the monthly usage left, in dollars.",
  tavily: "Searches the web for VFX and production studios using generative AI (company discovery). One credit per search.",
  groq: "Drafts suggestion text for review (never approves anything). Groq reports requests left today, shown after a real request.",
};
const STATE_HELP: Record<string, string> = {
  usable: "valid and has credit", low: "below the $0.80 floor for paid steps", out: "out of credit or rate-limited", dead: "invalid or revoked",
  error: "the last check failed (network); the previous balance is kept", unchecked: "not checked yet",
};

function amount(p: Provider, k: KeyRow, id: string) {
  if (k.remaining == null) return "—";
  return id === "apify" ? `$${k.remaining.toFixed(2)}${k.cap ? ` / $${k.cap}` : ""}` : `${Math.round(k.remaining)}${k.cap ? ` / ${Math.round(k.cap)}` : ""} ${p.unit}`;
}

function KeyLine({ id, p, k, onChanged }: { id: string; p: Provider; k: KeyRow; onChanged: (d: KeysInfo) => void }) {
  const [mode, setMode] = useState<"" | "replace" | "remove">("");
  const [val, setVal] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const act = async (f: () => Promise<KeysInfo>) => {
    setErr(null);
    try { onChanged(await f()); setMode(""); setVal(""); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <>
      <tr className="border-t border-line">
        <td className="py-2 font-mono text-xs">{k.key_prefix}…</td>
        <td><Badge tone={statusTone(k.state)}>{k.state}</Badge>{k.in_use && <span className="ml-1"><Badge tone="info">in use</Badge></span>}</td>
        <td className="tabular-nums">{amount(p, k, id)}</td>
        <td className="text-xs text-muted">{k.resets ? `resets ${k.resets}` : ""}</td>
        <td className="text-xs text-muted">{ago(k.checked_at)}</td>
        <td className="whitespace-nowrap text-right">
          <Button kind="ghost" onClick={() => setMode(mode === "replace" ? "" : "replace")}>Replace</Button>
          <Button kind="ghost" disabled={k.in_use} onClick={() => setMode(mode === "remove" ? "" : "remove")}>Remove</Button>
        </td>
      </tr>
      {mode && (
        <tr><td colSpan={6} className="pb-3">
          <div className="space-y-2 rounded-lg border border-line bg-panel-2 p-3">
            {mode === "replace" ? (
              <>
                <div className="text-sm">Paste the new key. It is added first, then <span className="font-mono">{k.key_prefix}…</span> is removed. <code className="text-xs">.env</code> is backed up outside the project.</div>
                <input type="password" autoComplete="off" className={inputCls} placeholder={`${p.prefix}…`} value={val} onChange={(e) => setVal(e.target.value)} />
                <div className="flex gap-2"><Button kind="primary" disabled={!val.startsWith(p.prefix)} onClick={() => act(() => api.put(`/api/keys/${id}/${k.key_prefix}`, { key: val.trim() }))}>Replace key</Button><Button kind="ghost" onClick={() => setMode("")}>Cancel</Button></div>
              </>
            ) : (
              <>
                <div className="text-sm">Remove <span className="font-mono">{k.key_prefix}…</span> from <code className="text-xs">.env</code>? A backup of <code className="text-xs">.env</code> is kept outside the project; nothing else changes.</div>
                <div className="flex gap-2"><Button kind="danger" onClick={() => act(() => api.del(`/api/keys/${id}/${k.key_prefix}`))}>Remove key</Button><Button kind="ghost" onClick={() => setMode("")}>Cancel</Button></div>
              </>
            )}
            {err && <Alert tone="bad">{err}</Alert>}
          </div>
        </td></tr>
      )}
    </>
  );
}

function ProviderCard({ id, p, onChanged }: { id: string; p: Provider; onChanged: (d: KeysInfo) => void }) {
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [showAll, setShowAll] = useState(false);
  const add = async () => {
    setMsg(null);
    const ks = text.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);
    try {
      const r = await api.post<KeysInfo & { added: number }>(`/api/keys/${id}`, { keys: ks });
      onChanged(r); setText(""); setAdding(false);
      setMsg({ tone: "good", text: `${r.added} key(s) added and checked.` });
    } catch (e) { setMsg({ tone: "bad", text: (e as Error).message }); }
  };
  const order = { dead: 0, out: 1, low: 2, error: 3, unchecked: 4, usable: 5 } as Record<string, number>;
  const sorted = [...p.keys].sort((a, b) => (order[a.state] ?? 9) - (order[b.state] ?? 9) || (b.remaining ?? -1) - (a.remaining ?? -1));
  const shown = showAll ? sorted : sorted.slice(0, 8);
  const configured = p.configured > 0;
  return (
    <Card title={<span className="flex items-center gap-2">{p.label}<Badge tone={!configured ? "neutral" : p.warnings.some((w) => w.level === "error") ? "bad" : p.warnings.some((w) => w.level === "warning") ? "warn" : "good"}>
      {!configured ? "not configured" : p.usable ? "active" : "no usable key"}</Badge></span>}
      actions={<Button onClick={() => setAdding(!adding)}>{adding ? "Close" : "Add keys"}</Button>}>
      <p className="text-sm text-muted">{ABOUT[id]}</p>
      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Keys" value={`${p.usable}/${p.configured}`} hint="usable / configured" />
        <Stat label="Remaining" value={p.total_remaining == null ? "—" : id === "apify" ? `$${p.total_remaining.toFixed(2)}` : Math.round(p.total_remaining)} hint={id === "apify" ? "all keys" : p.unit} />
        <Stat label="Spent (30 days)" value={usd(p.usage.spent_30d_usd)} hint={`${usd(p.usage.spent_usd)} all time`} />
        <Stat label="Calls" value={p.usage.calls} hint={p.usage.last_used ? `last ${ago(p.usage.last_used)}` : "never used"} />
      </div>
      <div className="mt-3 space-y-1.5">
        {p.warnings.map((w, i) => <Alert key={i} tone={w.level === "error" ? "bad" : w.level === "warning" ? "warn" : "info"}>{w.message}</Alert>)}
        {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
      </div>
      {adding && (
        <div className="mt-3 space-y-2 rounded-lg border border-line bg-panel-2 p-3">
          <div className="text-sm">Paste one or more keys (one per line or comma-separated). They start with <span className="font-mono">{p.prefix}</span>. They are written to <code className="text-xs">.env</code> ({p.env_var}) after a backup, and are never shown again in full.</div>
          <textarea rows={3} className={cx(inputCls, "font-mono text-xs")} autoComplete="off" spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} placeholder={`${p.prefix}…`} />
          <Button kind="primary" disabled={!text.trim()} onClick={add}>Add and check</Button>
        </div>
      )}
      {configured && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted"><tr><th className="py-1">Key</th><th>Status</th><th>Remaining</th><th /><th>Checked</th><th /></tr></thead>
            <tbody>{shown.map((k) => <KeyLine key={k.key_prefix} id={id} p={p} k={k} onChanged={onChanged} />)}</tbody>
          </table>
          {sorted.length > 8 && <button className="mt-2 text-xs text-muted hover:text-text" onClick={() => setShowAll(!showAll)}>{showAll ? "Show fewer" : `Show all ${sorted.length} keys`}</button>}
        </div>
      )}
    </Card>
  );
}

/** One place for every API integration: status, balances, usage, warnings, and adding / replacing / removing keys. */
export function Keys() {
  const { data, error, setData } = useFetch<KeysInfo>("/api/keys");
  const [busy, setBusy] = useState(false);
  const [liveTavily, setLiveTavily] = useState(false);
  const [liveGroq, setLiveGroq] = useState(false);
  const [thr, setThr] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const check = async () => {
    setBusy(true); setErr(null);
    try { setData(await api.post<KeysInfo>("/api/keys/check", { live_tavily: liveTavily, live_groq: liveGroq })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const saveThr = async () => {
    if (thr == null) return;
    try { await api.put("/api/settings/low-credit", { threshold: thr }); setData(await api.get<KeysInfo>("/api/keys")); setThr(null); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <div className="space-y-4">
      <Card title="Status checks">
        <div className="flex flex-wrap items-center gap-4">
          <Button kind="primary" disabled={busy} onClick={check}>{busy ? "Checking…" : "Check all keys"}</Button>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={liveTavily} onChange={(e) => setLiveTavily(e.target.checked)} /> also one live Tavily search per key (1 credit each)</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={liveGroq} onChange={(e) => setLiveGroq(e.target.checked)} /> also read Groq's daily quota (1 tiny request per key)</label>
          <span className="ml-auto flex items-center gap-2 text-sm">
            Warn below
            <span className="w-20"><input type="number" min={0} className={inputCls} value={thr ?? data?.low_credit_threshold ?? 20} onChange={(e) => setThr(+e.target.value)} aria-label="Low-credit threshold" /></span>
            credits / requests
            <Button disabled={thr == null} onClick={saveThr}>Save</Button>
          </span>
        </div>
        <p className="mt-2 text-xs text-muted">The normal check is free for all three providers. {Object.entries(STATE_HELP).map(([k, v]) => `${k}: ${v}`).join(" · ")}.</p>
        {(err || error) && <div className="mt-2"><Alert tone="bad">{err || error}</Alert></div>}
        {data?.demo && <div className="mt-2"><Alert tone="warn">Demo mode is on: fake Apify keys are shown and no network calls are made.</Alert></div>}
      </Card>
      {data && ["groq", "tavily", "apify"].map((id) => data.providers[id] && <ProviderCard key={id} id={id} p={data.providers[id]} onChanged={setData} />)}
    </div>
  );
}
