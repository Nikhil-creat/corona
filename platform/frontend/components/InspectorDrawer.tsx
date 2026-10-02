"use client";
import { useStore } from "@/lib/store";
import { set } from "@/lib/store";

function Sparkline({ values, max = 120 }: { values: number[]; max?: number }) {
  if (values.length < 2) return <div className="h-14 text-xs text-slate-500">collecting…</div>;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${40 - Math.min(v / max, 1) * 38}`).join(" ");
  return (
    <svg viewBox="0 0 100 40" className="h-14 w-full" preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="#38bdf8" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

const KIND_STYLE: Record<string, string> = {
  thought: "text-slate-400", result: "text-sky-300", escalation: "text-amber-300", status: "text-emerald-300",
};

export default function InspectorDrawer() {
  const id = useStore((s) => s.selected);
  const topo = useStore((s) => s.topology);
  const tel = useStore((s) => (id ? s.nodes[id] : undefined));
  const hist = useStore((s) => (id ? s.history[id] : undefined)) ?? [];
  const status = useStore((s) => (id ? s.nodeStatus[id] : undefined)) ?? "nominal";
  const anomaly = useStore((s) => (id ? s.anomalies.find((a) => a.node_id === id) : undefined));
  const trace = useStore((s) => (id && s.nodeThread[id] ? s.swarm[s.nodeThread[id]!] : undefined)) ?? [];
  if (!id) return null;
  const meta = topo?.nodes.find((n) => n.id === id);

  return (
    <aside className="pointer-events-auto absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-edge bg-panel/95 p-4 backdrop-blur md:w-[26rem]">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs text-neon">{id}</p>
          <h2 className="text-lg font-semibold">{meta?.name ?? "Node"}</h2>
          <p className="text-xs uppercase tracking-wider text-slate-400">status: {status.replace("_", " ")}</p>
        </div>
        <button className="rounded border border-edge px-2 py-1 text-xs hover:bg-edge" onClick={() => set({ selected: null })}>close</button>
      </div>

      <section className="mt-4 grid grid-cols-3 gap-2 text-center">
        {[["Temp", tel?.temperature_c, "°C"], ["Vibration", tel?.vibration_mm_s, "mm/s"], ["Stress", tel?.stress_pct, "%"]].map(([l, v, u]) => (
          <div key={l as string} className="rounded border border-edge p-2">
            <p className="text-[10px] uppercase text-slate-500">{l}</p>
            <p className="font-mono text-base">{typeof v === "number" ? v.toFixed(1) : "–"}<span className="text-xs text-slate-500"> {u}</span></p>
          </div>
        ))}
      </section>

      <section className="mt-4">
        <h3 className="mb-1 text-xs uppercase tracking-wider text-slate-400">Temperature (live)</h3>
        <Sparkline values={hist} />
      </section>

      <section className="mt-4">
        <h3 className="mb-1 text-xs uppercase tracking-wider text-slate-400">Vision overlay</h3>
        <div className="relative aspect-video overflow-hidden rounded border border-edge bg-[radial-gradient(circle_at_30%_40%,#1f2d4d,#0a0f1d)]">
          {anomaly?.detections.map((d, i) => (
            <div key={i} className="absolute border-2 border-danger" style={{ left: `${d.bbox[0] * 100}%`, top: `${d.bbox[1] * 100}%`, width: `${d.bbox[2] * 100}%`, height: `${d.bbox[3] * 100}%` }}>
              <span className="absolute -top-5 left-0 whitespace-nowrap bg-danger px-1 font-mono text-[10px] text-black">{d.label} {(d.confidence * 100).toFixed(0)}%</span>
            </div>
          )) ?? null}
          {!anomaly && <p className="absolute inset-0 grid place-items-center text-xs text-slate-500">no active detections</p>}
        </div>
      </section>

      <section className="mt-4">
        <h3 className="mb-1 text-xs uppercase tracking-wider text-slate-400">Swarm reasoning trace</h3>
        <ol className="space-y-1.5">
          {trace.length === 0 && <li className="text-xs text-slate-500">No agent thread for this node yet.</li>}
          {trace.map((e, i) => (
            <li key={i} className="rounded border border-edge/70 p-2 text-xs">
              <span className="font-mono text-[10px] text-slate-500">{new Date(e.ts * 1000).toLocaleTimeString()} · </span>
              <span className="font-semibold text-slate-200">{e.agent}</span>
              <p className={KIND_STYLE[e.kind]}>{e.message}</p>
            </li>
          ))}
        </ol>
      </section>
    </aside>
  );
}
