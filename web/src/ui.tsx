import type { ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-line bg-panel", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold tracking-wide text-text">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

type Tone = "neutral" | "good" | "warn" | "bad" | "accent" | "info";
const TONE: Record<Tone, string> = {
  neutral: "bg-panel-2 text-muted border-line",
  good: "bg-good/10 text-good border-good/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  bad: "bg-bad/10 text-bad border-bad/30",
  accent: "bg-accent/10 text-accent border-accent/30",
  info: "bg-accent-2/10 text-accent-2 border-accent-2/30",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium", TONE[tone])}>{children}</span>;
}

export function statusTone(s: string): Tone {
  if (["done", "usable", "approved", "AUTO_PASS"].includes(s)) return "good";
  if (["running", "queued"].includes(s)) return "info";
  if (["failed", "dead", "rejected", "error"].includes(s)) return "bad";
  if (["interrupted", "cancelled", "low", "out", "look", "paused_quota", "unchecked"].includes(s)) return "warn";
  return "neutral";
}

export function Button({ children, onClick, disabled, kind = "default", type = "button", title }: {
  children: ReactNode; onClick?: () => void; disabled?: boolean; kind?: "default" | "primary" | "danger" | "ghost"; type?: "button" | "submit"; title?: string;
}) {
  const k = {
    default: "border-line bg-panel-2 hover:bg-line text-text",
    primary: "border-accent bg-accent text-ink hover:brightness-110 font-semibold",
    danger: "border-bad/40 bg-bad/10 text-bad hover:bg-bad/20",
    ghost: "border-transparent bg-transparent text-muted hover:text-text",
  }[kind];
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={cx("inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40", k)}>
      {children}
    </button>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  const c = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "good" ? "text-good" : "text-text";
  return (
    <div className="rounded-lg border border-line bg-panel-2 px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={cx("mt-0.5 text-xl font-semibold tabular-nums", c)}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Alert({ tone, children }: { tone: "info" | "warn" | "bad" | "good"; children: ReactNode }) {
  const c = { info: "border-accent-2/30 bg-accent-2/5 text-accent-2", warn: "border-warn/30 bg-warn/5 text-warn", bad: "border-bad/30 bg-bad/5 text-bad", good: "border-good/30 bg-good/5 text-good" }[tone];
  return <div className={cx("rounded-lg border px-3 py-2 text-sm", c)}>{children}</div>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="text-xs text-muted">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-0.5 block text-[11px] text-muted/80">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-lg border border-line bg-ink px-2.5 py-1.5 text-sm text-text outline-none focus:border-accent-2";

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-panel-2">
      <div className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2 transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-6 text-center text-sm text-muted">{children}</div>;
}

/** Page text arrives with HTML entities (&#8216; &amp; ...): show the characters, never interpret markup. */
export function decode(s: string): string {
  const t = document.createElement("textarea");
  t.innerHTML = s;
  return t.value;
}

export const usd = (n: number | null | undefined, d = 3) => (n == null ? "—" : `$${n.toFixed(d)}`);

export function ago(ts: string | null | undefined): string {
  if (!ts) return "—";
  const t = new Date(ts.replace(" ", "T") + (ts.endsWith("Z") ? "" : "Z")).getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
