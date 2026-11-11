import type { Health, KeysInfo } from "../api";
import { Badge, cx } from "../ui";

/** Quick API health: one chip per provider plus the things that block work (stuck jobs, read-only sheet, demo mode). */
export function HealthStrip({ health, keys, connected, onKeys }: { health: Health | null; keys: KeysInfo | null; connected: boolean; onKeys: () => void }) {
  const provs = keys ? Object.entries(keys.providers) : [];
  return (
    <div className="flex flex-wrap items-center gap-2">
      {provs.map(([id, p]) => {
        const worst = p.warnings.some((w) => w.level === "error") ? "bad" : p.warnings.some((w) => w.level === "warning") ? "warn" : p.configured ? "good" : "neutral";
        const dot = { bad: "bg-bad", warn: "bg-warn", good: "bg-good", neutral: "bg-muted" }[worst];
        const amount = p.total_remaining == null ? "" : id === "apify" ? ` · $${p.total_remaining.toFixed(2)}` : ` · ${Math.round(p.total_remaining)} ${p.unit}`;
        return (
          <button key={id} onClick={onKeys} title={p.warnings.map((w) => w.message).join("\n") || "OK"}
            className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1 text-xs hover:border-accent-2">
            <span className={cx("h-2 w-2 rounded-full", dot)} />
            <span className="font-medium">{p.label}</span>
            <span className="text-muted">{p.configured ? `${p.usable}/${p.configured} usable${amount}` : "not configured"}</span>
          </button>
        );
      })}
      {health && (
        <>
          <Badge tone={health.sheet_target === "real" ? "bad" : health.sheet_target === "real_readonly" ? "info" : "neutral"}>
            sheet: {health.sheet_target === "real_readonly" ? "real (read-only)" : health.sheet_target}
          </Badge>
          {health.demo && <Badge tone="warn">DEMO MODE</Badge>}
          {health.stuck_jobs.length > 0 && <Badge tone="bad">{health.stuck_jobs.length} stuck job(s)</Badge>}
          {health.interrupted_jobs > 0 && <Badge tone="warn">{health.interrupted_jobs} interrupted</Badge>}
        </>
      )}
      <span className={cx("ml-auto flex items-center gap-1.5 text-xs", connected ? "text-good" : "text-muted")}>
        <span className={cx("h-1.5 w-1.5 rounded-full", connected ? "bg-good animate-pulse" : "bg-muted")} />
        {connected ? "live" : "reconnecting…"}
      </span>
    </div>
  );
}
