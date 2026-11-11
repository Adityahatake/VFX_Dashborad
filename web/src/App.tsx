import { lazy, Suspense, useEffect, useState } from "react";
import { Home } from "./home/Home";
import { Keys } from "./keys/Keys";
import { cx } from "./ui";

// Charts load only when opened. If the app was rebuilt while this tab was open, the old chunk is gone: reload once to get the new build.
const Analytics = lazy(() => import("./analytics/Analytics").then((m) => ({ default: m.Analytics })).catch((e) => {
  try {
    if (!sessionStorage.getItem("chunk-reload")) { sessionStorage.setItem("chunk-reload", "1"); window.location.reload(); }
  } catch { /* storage blocked: fall through to the error */ }
  throw e;
}));

type Page = "home" | "analytics" | "keys";
const PAGES: [Page, string][] = [["home", "Home"], ["analytics", "Analytics"], ["keys", "API & Keys"]];

function fromHash(): Page {
  const h = window.location.hash.replace("#/", "");
  return (PAGES.find(([p]) => p === h)?.[0] ?? "home") as Page;
}

export default function App() {
  const [page, setPage] = useState<Page>(fromHash);
  useEffect(() => {
    const t = setTimeout(() => { try { sessionStorage.removeItem("chunk-reload"); } catch { /* ignore */ } }, 10000);   // a later rebuild may reload again
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    const f = () => setPage(fromHash());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const go = (p: Page) => { window.location.hash = `#/${p}`; };

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-line bg-ink/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] items-center gap-6 px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-accent to-accent-2 text-[11px] font-black text-ink">VFX</div>
            <div className="leading-tight">
              <div className="text-sm font-semibold">VFX Lead Ops</div>
              <div className="text-[11px] text-muted">studios using GenAI in client work</div>
            </div>
          </div>
          <nav className="flex gap-1">
            {PAGES.map(([p, label]) => (
              <button key={p} onClick={() => go(p)}
                className={cx("rounded-lg px-3 py-1.5 text-sm", page === p ? "bg-panel-2 text-text" : "text-muted hover:text-text")}>{label}</button>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] px-4 py-5">
        {page === "home" && <Home goKeys={() => go("keys")} />}
        {page === "analytics" && <Suspense fallback={<div className="text-sm text-muted">Loading charts…</div>}><Analytics /></Suspense>}
        {page === "keys" && <Keys />}
      </main>
    </div>
  );
}

