import { useEffect, useRef, useState } from "react";
import { api } from "../api";

/** The technical log, hidden until asked for. While a job runs it refreshes every 2 s. Logs are key-masked on the server. */
export function LogView({ jobId, live }: { jobId: number; live: boolean }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const box = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (!open) return;
    let stop = false;
    const load = async () => {
      try {
        const r = await api.get<{ log: string }>(`/api/jobs/${jobId}/log?lines=400`);
        if (!stop) setText(r.log || "(no output yet)");
      } catch (e) { if (!stop) setText(`could not load the log: ${(e as Error).message}`); }
    };
    load();
    const t = live ? setInterval(load, 2000) : undefined;
    return () => { stop = true; if (t) clearInterval(t); };
  }, [open, jobId, live]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [text]);
  return (
    <div className="mt-3">
      <button className="text-xs text-muted hover:text-text" onClick={() => setOpen(!open)}>{open ? "▾ Hide technical log" : "▸ Show technical log"}</button>
      {open && <pre ref={box} className="mt-2 max-h-80 overflow-auto rounded-lg border border-line bg-ink p-3 font-mono text-[11px] leading-relaxed text-muted whitespace-pre-wrap">{text}</pre>}
    </div>
  );
}
