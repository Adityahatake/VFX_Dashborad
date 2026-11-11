import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { KeysInfo } from "../api";
import { useFetch } from "../hooks";
import { Alert, Button, Card, cx, Empty, inputCls, Stat, usd } from "../ui";

// Categorical slots (validated on the dark surface #121722: lightness, chroma, CVD >= 8.4, contrast >= 3:1). Fixed order, never cycled.
const SLOT = ["#3987e5", "#d95926", "#199e70", "#c98500"];
const SURFACE = "#121722";
const PROVIDER_COLOR: Record<string, string> = { apify: SLOT[0], tavily: SLOT[1], llm: SLOT[2], groq: SLOT[3] };
const PROVIDER_LABEL: Record<string, string> = { apify: "Apify", tavily: "Tavily", llm: "AI (Anthropic)", groq: "Groq" };

type Row = Record<string, number | string>;
type Summary = {
  totals: {
    companies: number; companies_qualified: number; people: number; people_approved: number; rows_appended: number; runs: number;
    runs_by_status: Record<string, number>; avg_run_minutes: number | null; people_per_qualified_company: number | null; spend_usd: number;
  };
  collection: Record<"today" | "last_7_days" | "last_30_days", { companies: number; people: number }>;
  series: { companies: Row[]; people: Row[]; spend: Row[]; runs: Row[] };
  spend_by_kind: Record<string, { usd: number; calls: number; results: number }>;
  runs: { job_id: number; status: string; started_at: string; minutes: number | null; spent_usd: number; companies_found: number; companies_qualified: number;
    people_found: number; people_valid: number; records_saved: number; records_skipped: number; errors: number }[];
  steps: { step_id: string; n: number; done: number; failed: number }[];
};

const iso = (d: Date) => d.toISOString().slice(0, 10);
const RANGES: [string, number | null][] = [["7 days", 7], ["30 days", 30], ["90 days", 90], ["All time", null]];

type Series = { key: string; label: string; color: string };

/** A stacked bar chart over time with a legend, per-bar tooltips, and a table view of the same numbers. */
function TimeBars({ title, data, series, money }: { title: string; data: Row[]; series: Series[]; money?: boolean }) {
  const [table, setTable] = useState(false);
  const fmt = (v: number) => (money ? `$${v.toFixed(3)}` : String(v));
  const rows = data.map((r) => ({ ...r, ...Object.fromEntries(series.map((s) => [s.key, Number(r[s.key] ?? 0)])) }));
  const empty = rows.length === 0 || rows.every((r) => series.every((s) => !r[s.key]));
  return (
    <Card title={title} actions={<Button kind="ghost" onClick={() => setTable(!table)}>{table ? "Chart" : "Table"}</Button>}>
      {empty ? <Empty>No data in this range.</Empty> : table ? (
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted"><tr><th className="py-1">Period</th>{series.map((s) => <th key={s.key} className="text-right">{s.label}</th>)}</tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={String(r.bucket)} className="border-t border-line"><td className="py-1">{String(r.bucket)}</td>
                {series.map((s) => <td key={s.key} className="text-right tabular-nums">{fmt(Number(r[s.key]))}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 4, left: -8, bottom: 0 }} barCategoryGap="24%">
              <CartesianGrid vertical={false} stroke="#253046" strokeDasharray="0" strokeOpacity={0.6} />
              <XAxis dataKey="bucket" tick={{ fill: "#8b97ad", fontSize: 11 }} axisLine={{ stroke: "#253046" }} tickLine={false} />
              <YAxis tick={{ fill: "#8b97ad", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={!!money} tickFormatter={(v) => (money ? `$${v}` : v)} width={48} />
              <Tooltip cursor={{ fill: "#ffffff", fillOpacity: 0.04 }}
                contentStyle={{ background: "#0b0e14", border: "1px solid #253046", borderRadius: 8, fontSize: 12 }} labelStyle={{ color: "#e6ebf5" }}
                itemStyle={{ color: "#e6ebf5" }} formatter={(v: number, name: string) => [fmt(v), name]} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#8b97ad" }} iconType="plainline" />
              {series.map((s, i) => (
                <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} stroke={SURFACE} strokeWidth={2}
                  radius={i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} maxBarSize={28} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

export function Analytics() {
  const [days, setDays] = useState<number | null>(30);
  const [custom, setCustom] = useState<{ from: string; to: string } | null>(null);
  const [bucket, setBucket] = useState<"day" | "week" | "month">("day");
  const range = useMemo(() => {
    if (custom) return custom;
    if (days == null) return { from: "", to: "" };
    const to = new Date(), from = new Date(Date.now() - (days - 1) * 86400000);
    return { from: iso(from), to: iso(to) };
  }, [days, custom]);
  const q = new URLSearchParams({ bucket, ...(range.from ? { from: range.from } : {}), ...(range.to ? { to: range.to } : {}) }).toString();
  const { data: s, error } = useFetch<Summary>(`/api/analytics?${q}`, [], 60000);
  const { data: keys } = useFetch<KeysInfo>("/api/keys");

  const kinds = useMemo(() => {
    const k = new Set<string>(Object.keys(s?.spend_by_kind ?? {}));
    return ["apify", "tavily", "llm", "groq"].filter((x) => k.has(x)).concat([...k].filter((x) => !PROVIDER_COLOR[x]));
  }, [s]);
  const t = s?.totals;
  const decided = [{ key: "approved", label: "Approved", color: SLOT[0] }, { key: "rejected", label: "Rejected", color: SLOT[1] }, { key: "other", label: "Pending / held", color: SLOT[2] }];
  const withOther = (rows: Row[] = []) => rows.map((r) => ({ ...r, other: Number(r.n) - Number(r.approved ?? 0) - Number(r.rejected ?? 0) }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex rounded-lg border border-line p-0.5 text-sm">
          {RANGES.map(([l, d]) => (
            <button key={l} onClick={() => { setDays(d); setCustom(null); }}
              className={cx("rounded-md px-2.5 py-1", !custom && days === d ? "bg-panel-2 text-text" : "text-muted hover:text-text")}>{l}</button>
          ))}
        </div>
        <div className="w-40"><input type="date" className={inputCls} value={range.from} onChange={(e) => setCustom({ from: e.target.value, to: range.to || iso(new Date()) })} aria-label="From" /></div>
        <span className="pb-1.5 text-muted">→</span>
        <div className="w-40"><input type="date" className={inputCls} value={range.to} onChange={(e) => setCustom({ from: range.from, to: e.target.value })} aria-label="To" /></div>
        <div className="ml-auto flex rounded-lg border border-line p-0.5 text-sm">
          {(["day", "week", "month"] as const).map((b) => (
            <button key={b} onClick={() => setBucket(b)} className={cx("rounded-md px-2.5 py-1", bucket === b ? "bg-panel-2 text-text" : "text-muted hover:text-text")}>
              {b === "day" ? "Daily" : b === "week" ? "Weekly" : "Monthly"}</button>
          ))}
        </div>
      </div>
      {error && <Alert tone="bad">{error}</Alert>}
      {!s ? <div className="text-sm text-muted">Loading…</div> : (
        <>
          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Data collection</h2>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
              <Stat label="Companies discovered" value={t!.companies} hint={`${t!.companies_qualified} qualified`} />
              <Stat label="People discovered" value={t!.people} hint={`${t!.people_approved} approved`} />
              <Stat label="Rows added to sheet" value={t!.rows_appended} />
              <Stat label="People per qualified company" value={t!.people_per_qualified_company ?? "—"} hint="discovery conversion" />
              <Stat label="Spend in range" value={usd(t!.spend_usd)} />
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {(["today", "last_7_days", "last_30_days"] as const).map((k) => (
                <div key={k} className="rounded-lg border border-line bg-panel px-3 py-2 text-sm">
                  <span className="text-muted">{k === "today" ? "Today" : k === "last_7_days" ? "Last 7 days" : "Last 30 days"}: </span>
                  <b className="tabular-nums">{s.collection[k].companies}</b> companies · <b className="tabular-nums">{s.collection[k].people}</b> people
                </div>
              ))}
            </div>
          </section>
          <div className="grid gap-4 xl:grid-cols-2">
            <TimeBars title="Companies added" data={withOther(s.series.companies)} series={decided} />
            <TimeBars title="People added" data={withOther(s.series.people)} series={decided} />
          </div>

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Pipeline performance</h2>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <Stat label="Pipeline runs" value={t!.runs} />
              <Stat label="Successful" value={t!.runs_by_status.done ?? 0} />
              <Stat label="Failed" value={t!.runs_by_status.failed ?? 0} tone={(t!.runs_by_status.failed ?? 0) > 0 ? "bad" : undefined} />
              <Stat label="Average run time" value={t!.avg_run_minutes == null ? "—" : `${t!.avg_run_minutes.toFixed(1)} min`} hint="successful runs" />
            </div>
          </section>
          <div className="grid gap-4 xl:grid-cols-2">
            <TimeBars title="Pipeline runs" data={s.series.runs} series={[{ key: "done", label: "Successful", color: SLOT[0] }, { key: "failed", label: "Failed", color: SLOT[1] }, { key: "other", label: "Cancelled / running", color: SLOT[2] }]} />
            <Card title="Records processed per run">
              {s.runs.length === 0 ? <Empty>No pipeline runs in this range.</Empty> : (
                <div className="max-h-64 overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-muted"><tr><th className="py-1">Run</th><th className="text-right">Companies</th><th className="text-right">Qualified</th><th className="text-right">People</th><th className="text-right">Saved</th><th className="text-right">Skipped</th><th className="text-right">Time</th><th className="text-right">Spent</th></tr></thead>
                    <tbody>{[...s.runs].reverse().map((r) => (
                      <tr key={r.job_id} className="border-t border-line tabular-nums">
                        <td className="py-1">#{r.job_id} <span className="text-xs text-muted">{r.status}{r.errors ? ` · ${r.errors} err` : ""}</span></td>
                        <td className="text-right">{r.companies_found}</td><td className="text-right">{r.companies_qualified}</td><td className="text-right">{r.people_found}</td>
                        <td className="text-right">{r.records_saved}</td><td className="text-right">{r.records_skipped}</td>
                        <td className="text-right">{r.minutes == null ? "—" : `${r.minutes.toFixed(1)}m`}</td><td className="text-right">{usd(r.spent_usd)}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>

          <section>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">API usage and spending</h2>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <TimeBars title="Spend by provider" money data={s.series.spend} series={kinds.map((k, i) => ({ key: k, label: PROVIDER_LABEL[k] ?? k, color: PROVIDER_COLOR[k] ?? SLOT[i % SLOT.length] }))} />
              <Card title="Providers">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted"><tr><th className="py-1">Provider</th><th className="text-right">Calls</th><th className="text-right">Spent</th><th className="text-right">Remaining</th></tr></thead>
                  <tbody>
                    {["apify", "tavily", "groq"].map((p) => {
                      const sp = s.spend_by_kind[p], kp = keys?.providers[p];
                      const rem = kp?.total_remaining;
                      return (
                        <tr key={p} className="border-t border-line tabular-nums">
                          <td className="py-1.5"><span className="mr-2 inline-block h-0.5 w-3 align-middle" style={{ background: PROVIDER_COLOR[p] }} />{PROVIDER_LABEL[p]}</td>
                          <td className="text-right">{sp?.calls ?? 0}</td><td className="text-right">{usd(sp?.usd ?? 0)}</td>
                          <td className="text-right">{rem == null ? (kp?.configured ? "unknown" : "no keys") : p === "apify" ? `$${rem.toFixed(2)}` : `${Math.round(rem)} ${kp!.unit}`}</td>
                        </tr>
                      );
                    })}
                    {s.spend_by_kind.llm && <tr className="border-t border-line tabular-nums"><td className="py-1.5">{PROVIDER_LABEL.llm}</td><td className="text-right">{s.spend_by_kind.llm.calls}</td><td className="text-right">{usd(s.spend_by_kind.llm.usd)}</td><td className="text-right text-muted">—</td></tr>}
                  </tbody>
                </table>
                <div className="mt-3 space-y-1.5">
                  {keys && Object.values(keys.providers).flatMap((p) => p.warnings.filter((w) => w.level !== "info")).map((w, i) => (
                    <Alert key={i} tone={w.level === "error" ? "bad" : "warn"}>{w.message}</Alert>
                  ))}
                </div>
                <p className="mt-2 text-xs text-muted">Spend comes from the spend ledger (including the imported VFX history). Remaining credit is the latest balance check.</p>
              </Card>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
