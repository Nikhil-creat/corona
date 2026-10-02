import { Approval, Topology } from "./schemas";
import { z } from "zod";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const WS_URL = `${process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"}/ws/stream?key=${encodeURIComponent(process.env.NEXT_PUBLIC_API_KEY ?? "")}`;
const headers = () => ({ "X-API-Key": process.env.NEXT_PUBLIC_API_KEY ?? "", "Content-Type": "application/json" });

async function j<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const r = await fetch(`${API}${path}`, { headers: headers() });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return schema.parse(await r.json());
}

export const fetchTopology = () => j("/api/topology", Topology);
export const fetchPending = () => j("/api/approvals/pending", z.array(Approval));

export async function decide(a: Approval, approve: boolean, approver: string, token: string): Promise<void> {
  const r = await fetch(`${API}/api/approvals/${a.thread_id}/decision`, {
    method: "POST", headers: headers(),
    body: JSON.stringify({ approve, approver, nonce: a.nonce, token }),
  });
  if (!r.ok) throw new Error(r.status === 403 ? "Approver credentials rejected" : `Decision failed (${r.status})`);
}

export async function injectAnomaly(node_id: string, label: string, severity: number): Promise<void> {
  await fetch(`${API}/api/dev/inject-anomaly`, { method: "POST", headers: headers(), body: JSON.stringify({ node_id, label, severity }) });
}
