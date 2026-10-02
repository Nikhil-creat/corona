"use client";
import { useEffect, useState } from "react";
import { decide } from "@/lib/api";
import { useStore } from "@/lib/store";

export default function ApprovalPanel() {
  const approvalMap = useStore((s) => s.approvals);
  const approvals = Object.values(approvalMap);
  const [approver, setApprover] = useState("ops-lead");
  const [token, setToken] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => { setToken(sessionStorage.getItem("aether.token") ?? ""); }, []);
  useEffect(() => { sessionStorage.setItem("aether.token", token); }, [token]);

  if (approvals.length === 0) return null;
  return (
    <div className="pointer-events-auto absolute bottom-4 left-4 w-[22rem] rounded-lg border border-amber2/50 bg-panel/95 p-3 backdrop-blur">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-amber2">Human approval required ({approvals.length})</h3>
      <div className="mb-2 flex gap-2">
        <input className="w-1/2 rounded border border-edge bg-void px-2 py-1 text-xs" value={approver} onChange={(e) => setApprover(e.target.value)} aria-label="approver" />
        <input className="w-1/2 rounded border border-edge bg-void px-2 py-1 text-xs" type="password" placeholder="approver token" value={token} onChange={(e) => setToken(e.target.value)} />
      </div>
      <ul className="max-h-64 space-y-2 overflow-y-auto">
        {approvals.map((a) => (
          <li key={a.thread_id} className="rounded border border-edge p-2 text-xs">
            <p><span className="font-mono text-neon">{a.node_id}</span> · <b>{a.plan.action}</b> {JSON.stringify(a.plan.params)}</p>
            <p className="text-slate-400">risk {a.risk.toFixed(2)} · {a.plan.physical ? "physical intervention" : "software action"} · {a.plan.citations.length} citation(s)</p>
            <div className="mt-2 flex gap-2">
              {[true, false].map((ok) => (
                <button key={String(ok)} disabled={busy === a.thread_id}
                  className={`rounded px-2 py-1 font-semibold ${ok ? "bg-ok text-black" : "bg-danger text-black"} disabled:opacity-50`}
                  onClick={async () => {
                    setBusy(a.thread_id); setMsg(null);
                    try { await decide(a, ok, approver, token); } catch (e) { setMsg((e as Error).message); } finally { setBusy(null); }
                  }}>{ok ? "Approve" : "Reject"}</button>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {msg && <p className="mt-2 text-xs text-danger">{msg}</p>}
    </div>
  );
}
