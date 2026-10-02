/// Off-main-thread: owns the WebSocket, validates every frame with zod and batches at ~10 Hz.
import { StreamMessage } from "../lib/schemas";

const ctx = self as unknown as Worker;
let ws: WebSocket | null = null;
let buffer: unknown[] = [];
let retry = 0;
let url = "";

function connect() {
  ws = new WebSocket(url);
  ws.onopen = () => { retry = 0; ctx.postMessage({ kind: "conn", connected: true }); };
  ws.onclose = () => {
    ctx.postMessage({ kind: "conn", connected: false });
    setTimeout(connect, Math.min(1000 * 2 ** retry++, 15000));
  };
  ws.onmessage = (e) => {
    try {
      const parsed = StreamMessage.safeParse(JSON.parse(e.data as string));
      if (parsed.success) buffer.push(parsed.data);
    } catch { /* ignore malformed frame */ }
  };
}

setInterval(() => {
  if (buffer.length) { ctx.postMessage({ kind: "batch", messages: buffer }); buffer = []; }
}, 100);

ctx.onmessage = (e: MessageEvent<{ url: string }>) => { url = e.data.url; connect(); };
