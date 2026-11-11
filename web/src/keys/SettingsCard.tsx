import { useEffect, useState } from "react";
import { api } from "../api";
import { useFetch } from "../hooks";
import { Alert, Button, Card, cx, Field, inputCls } from "../ui";

type Settings = {
  demo_mode: boolean; default_cap_usd: number; hard_max_cap_usd: number; llm_enabled: boolean; llm_model: string; llm_cycle_cap_usd: number;
  llm_prices: Record<string, Record<string, number>>; env: Record<string, string>; paths: Record<string, string>;
};

/** Settings that used to live on their own page: demo mode, the default cap, AI suggestions, and what is configured in .env (prefix only). */
export function SettingsCard() {
  const { data, setData } = useFetch<Settings>("/api/settings");
  const [form, setForm] = useState<Partial<Settings>>({});
  const [prices, setPrices] = useState("");
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => { if (data) { setForm({}); setPrices(JSON.stringify(data.llm_prices, null, 1)); } }, [data]);
  if (!data) return null;
  const v = { ...data, ...form };
  const save = async (extra: Partial<Settings> = {}) => {
    setMsg(null);
    try {
      let p: Settings["llm_prices"] | undefined;
      if (open) { try { p = JSON.parse(prices); } catch { throw new Error("The price table is not valid JSON"); } }
      setData(await api.put<Settings>("/api/settings", { ...form, ...extra, ...(p ? { llm_prices: p } : {}) }));
      setMsg({ tone: "good", text: "Saved." });
    } catch (e) { setMsg({ tone: "bad", text: (e as Error).message }); }
  };
  return (
    <Card title="Settings">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={v.demo_mode} onChange={(e) => save({ demo_mode: e.target.checked })} />
            <span><b>Demo mode</b><br /><span className="text-muted">Fake Apify keys, an in-memory sheet and no network calls, for training and testing. Never for real runs. Switching clears stored balances.</span></span>
          </label>
          <Field label={`Default cycle spend cap (USD, never above $${data.hard_max_cap_usd.toFixed(2)})`}>
            <input type="number" min={0} step={0.25} className={inputCls} value={v.default_cap_usd} onChange={(e) => setForm({ ...form, default_cap_usd: +e.target.value })} />
          </Field>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={v.llm_enabled} onChange={(e) => setForm({ ...form, llm_enabled: e.target.checked })} />
            <span><b>AI suggestions</b><br /><span className="text-muted">Drafts only: every company and person still needs your decision.</span></span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Model"><input className={inputCls} value={v.llm_model} onChange={(e) => setForm({ ...form, llm_model: e.target.value })} /></Field>
            <Field label="AI cap per cycle (USD)"><input type="number" min={0} step={0.25} className={inputCls} value={v.llm_cycle_cap_usd} onChange={(e) => setForm({ ...form, llm_cycle_cap_usd: +e.target.value })} /></Field>
          </div>
          <button className="text-xs text-muted hover:text-text" onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} AI price table (USD per 1M tokens)</button>
          {open && <textarea rows={6} className={cx(inputCls, "font-mono text-xs")} value={prices} onChange={(e) => setPrices(e.target.value)} spellCheck={false} />}
          <div className="flex items-center gap-2"><Button kind="primary" onClick={() => save()}>Save settings</Button>{msg && <Alert tone={msg.tone}>{msg.text}</Alert>}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-muted">Configured in .env (never shown in full)</div>
          <table className="mt-1 w-full text-sm">
            <tbody>{Object.entries(data.env).map(([k, val]) => (
              <tr key={k} className="border-t border-line"><td className="py-1.5 font-mono text-xs">{k}</td><td className={cx("text-right text-xs", val.startsWith("not set") || val.includes("NOT") ? "text-warn" : "text-muted")}>{val}</td></tr>
            ))}</tbody>
          </table>
          <div className="mt-3 text-xs text-muted">Database: <span className="font-mono">{data.paths.database}</span></div>
        </div>
      </div>
    </Card>
  );
}
