import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Snapshot } from "./api";

/** GET a path, with a reload function. `deps` re-fetch when they change; `everyMs` polls. */
export function useFetch<T>(path: string | null, deps: unknown[] = [], everyMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const alive = useRef(true);
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      const d = await api.get<T>(path);
      if (alive.current) { setData(d); setError(null); }
    } catch (e) {
      if (alive.current) setError((e as Error).message);
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => {
    alive.current = true;
    load();
    const t = everyMs ? setInterval(load, everyMs) : undefined;
    return () => { alive.current = false; if (t) clearInterval(t); };
  }, [load, everyMs]);
  return { data, error, loading, reload: load, setData };
}

/** Live job / spend / pipeline-progress snapshots from the server (Server-Sent Events), with automatic reconnect. */
export function useLive() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const open = () => {
      es = new EventSource("/api/events");
      es.addEventListener("snapshot", (e) => { setSnap(JSON.parse((e as MessageEvent).data)); setConnected(true); });
      es.onerror = () => { setConnected(false); es?.close(); retry = setTimeout(open, 3000); };
    };
    open();
    return () => { es?.close(); if (retry) clearTimeout(retry); };
  }, []);
  return { snap, connected };
}
