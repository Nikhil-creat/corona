import { useSyncExternalStore } from "react";
import type { Anomaly, Approval, StreamMessage, SwarmEvent, Telemetry, Topology } from "./schemas";

export type NodeStatus = "nominal" | "investigating" | "awaiting_approval" | "remediated" | "escalated";

export interface State {
  connected: boolean;
  topology: Topology | null;
  nodes: Record<string, Telemetry>;
  history: Record<string, number[]>;
  anomalies: Anomaly[];
  swarm: Record<string, SwarmEvent[]>;      // by thread
  nodeThread: Record<string, string>;        // latest thread per node
  nodeStatus: Record<string, NodeStatus>;
  approvals: Record<string, Approval>;
  flVersion: number;
  selected: string | null;
}

let state: State = {
  connected: false, topology: null, nodes: {}, history: {}, anomalies: [], swarm: {},
  nodeThread: {}, nodeStatus: {}, approvals: {}, flVersion: 0, selected: null,
};
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export const set = (patch: Partial<State>) => { state = { ...state, ...patch }; emit(); };
export const get = () => state;

const STATUS_MAP: Record<string, NodeStatus> = {
  investigating: "investigating", awaiting_approval: "awaiting_approval", remediated: "remediated",
  escalated: "escalated", false_positive: "nominal", rejected_by_human: "escalated",
};

export function applyBatch(messages: StreamMessage[]) {
  const s = { ...state, nodes: { ...state.nodes }, history: { ...state.history }, swarm: { ...state.swarm },
    nodeThread: { ...state.nodeThread }, nodeStatus: { ...state.nodeStatus }, approvals: { ...state.approvals } };
  let anomalies = state.anomalies;
  for (const m of messages) {
    switch (m.type) {
      case "telemetry.raw": {
        s.nodes[m.data.node_id] = m.data;
        const h = (s.history[m.data.node_id] ?? []).concat(m.data.temperature_c);
        s.history[m.data.node_id] = h.slice(-90);
        break;
      }
      case "anomalies.detected":
        anomalies = [m.data, ...anomalies].slice(0, 100);
        s.nodeThread[m.data.node_id] = m.data.id;
        break;
      case "swarm.events": {
        const e = m.data;
        s.swarm[e.thread_id] = [...(s.swarm[e.thread_id] ?? []), e].slice(-120);
        s.nodeThread[e.node_id] = e.thread_id;
        const st = typeof e.data.status === "string" ? STATUS_MAP[e.data.status] : undefined;
        if (st) s.nodeStatus[e.node_id] = st;
        if (st === "remediated" || e.data.status === "rejected_by_human") delete s.approvals[e.thread_id];
        break;
      }
      case "approvals.requests": s.approvals[m.data.thread_id] = m.data; break;
      case "fl.global": s.flVersion = m.data.version; break;
      default: break;
    }
  }
  state = { ...s, anomalies };
  emit();
}

export function useStore<T>(selector: (s: State) => T): T {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => selector(state),
    () => selector(state),
  );
}
