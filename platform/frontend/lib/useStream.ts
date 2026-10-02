"use client";
import { useEffect } from "react";
import { fetchPending, fetchTopology, WS_URL } from "./api";
import { applyBatch, set } from "./store";
import type { StreamMessage } from "./schemas";

export function useStream() {
  useEffect(() => {
    let worker: Worker | null = null;
    fetchTopology().then((topology) => set({ topology })).catch(console.error);
    fetchPending().then((list) => set({ approvals: Object.fromEntries(list.map((a) => [a.thread_id, a])) })).catch(console.error);
    worker = new Worker(new URL("../workers/stream.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (e: MessageEvent<{ kind: string; connected?: boolean; messages?: StreamMessage[] }>) => {
      if (e.data.kind === "conn") set({ connected: !!e.data.connected });
      else if (e.data.messages) applyBatch(e.data.messages);
    };
    worker.postMessage({ url: WS_URL });
    return () => worker?.terminate();
  }, []);
}
