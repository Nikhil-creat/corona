"use client";
import { injectAnomaly } from "@/lib/api";
import { useStore } from "@/lib/store";

export default function Hud() {
  const connected = useStore((s) => s.connected);
  const fl = useStore((s) => s.flVersion);
  const selected = useStore((s) => s.selected);
  const anomalies = useStore((s) => s.anomalies);
  const recent = anomalies.slice(0, 5);
  return (
    <header className="pointer-events-none absolute left-0 top-0 p-4">
      <h1 className="text-lg font-semibold tracking-tight">Corona<span className="text-neon">-Quantum</span></h1>
      <p className="text-xs text-slate-400">Self-healing spatial digital twin</p>
      <div className="mt-2 flex items-center gap-3 text-xs">
        <span className={`inline-flex items-center gap-1 ${connected ? "text-ok" : "text-danger"}`}>
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-ok" : "bg-danger"}`} />{connected ? "live" : "reconnecting"}
        </span>
        <span className="text-slate-400">federated model v{fl}</span>
      </div>
      <ul className="mt-3 space-y-1 text-xs">
        {recent.map((a) => (
          <li key={a.id} className="font-mono text-amber2">⚠ {a.node_id} {a.label} · sev {a.severity.toFixed(2)}</li>
        ))}
      </ul>
      <button className="pointer-events-auto mt-3 rounded border border-edge px-2 py-1 text-xs text-slate-300 hover:bg-edge"
        onClick={() => injectAnomaly(selected ?? "N-01", "thermal_overheat", 0.8)}>
        inject test anomaly{selected ? ` on ${selected}` : ""}
      </button>
    </header>
  );
}
