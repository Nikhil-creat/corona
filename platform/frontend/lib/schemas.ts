import { z } from "zod";

export const Telemetry = z.object({
  node_id: z.string(), ts: z.number(),
  temperature_c: z.number(), vibration_mm_s: z.number(), stress_pct: z.number(),
});
export const Detection = z.object({
  label: z.string(), confidence: z.number(), bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
});
export const Anomaly = z.object({
  id: z.string(), node_id: z.string(), ts: z.number(), modality: z.string(), label: z.string(),
  severity: z.number(), confidence: z.number(), detections: z.array(Detection), telemetry: Telemetry.nullable(),
});
export const SwarmEvent = z.object({
  thread_id: z.string(), node_id: z.string(), agent: z.string(),
  kind: z.enum(["thought", "result", "escalation", "status"]), message: z.string(), ts: z.number(),
  data: z.record(z.unknown()),
});
export const Plan = z.object({
  action: z.string(), params: z.record(z.union([z.number(), z.string(), z.boolean()])),
  rationale: z.string(), citations: z.array(z.string()), physical: z.boolean(),
});
export const Approval = z.object({
  thread_id: z.string(), node_id: z.string(), plan: Plan, risk: z.number(),
  nonce: z.string(), created_at: z.number(), expires_at: z.number(),
});
export const Topology = z.object({
  nodes: z.array(z.object({ id: z.string(), name: z.string(), criticality: z.number(), x: z.number(), z: z.number() })),
  edges: z.array(z.tuple([z.string(), z.string()])),
});

export const StreamMessage = z.discriminatedUnion("type", [
  z.object({ type: z.literal("telemetry.raw"), data: Telemetry }),
  z.object({ type: z.literal("anomalies.detected"), data: Anomaly }),
  z.object({ type: z.literal("swarm.events"), data: SwarmEvent }),
  z.object({ type: z.literal("approvals.requests"), data: Approval }),
  z.object({ type: z.literal("remediation.executed"), data: z.object({ thread_id: z.string(), node_id: z.string() }).passthrough() }),
  z.object({ type: z.literal("fl.global"), data: z.object({ version: z.number(), clients: z.number() }) }),
]);

export type Telemetry = z.infer<typeof Telemetry>;
export type Anomaly = z.infer<typeof Anomaly>;
export type SwarmEvent = z.infer<typeof SwarmEvent>;
export type Approval = z.infer<typeof Approval>;
export type Topology = z.infer<typeof Topology>;
export type StreamMessage = z.infer<typeof StreamMessage>;
