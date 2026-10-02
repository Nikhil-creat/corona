# Corona
**Autonomous Cyber-Physical Spatial Intelligence & Self-Healing Digital Twin Ecosystem**

A web-native 3D digital twin that watches a facility through edge vision + IoT telemetry, detects anomalies, and dispatches an
isolated, deterministic multi-agent swarm that **validates → grounds itself in authoritative manuals → scores risk → plans → verifies → asks a
human to cryptographically sign off on anything physical → executes**.

Built by Nikhil Chary Sriramoju.

```
 RTSP / IoT ──► edge-vision ──► Redpanda (Kafka) ──┬──► api (FastAPI: REST · WebSocket · gRPC) ──► Next.js + R3F twin
   (ViT+CNN)     telemetry.raw / anomalies.detected │                                                  ▲   │ signed approval
                 fl.updates ◄── federated clients   └──► worker (LangGraph swarm) ──► swarm.events ───┘   ▼
                                                          │  Validator → Compliance-RAG → Risk → Planner ⇄ Verifier → HITL gate → Execute
                                   pgvector (chunks) ◄────┤  Neo4j temporal graph (aging · failures · time-bounded dependencies)
                                   Redis (state · checkpoints · nonces)
                  OpenTelemetry → Jaeger │ Prometheus → Grafana
```

## Repository layout
| Path | Contents |
|---|---|
| `frontend/` | Next.js 15 (App Router) · TypeScript strict · Tailwind · React Three Fiber · Web Worker WebSocket client · zod-validated stream · GLSL shaders |
| `backend/` | FastAPI app (`app/`), routers, DI, WebSocket hub, gRPC client-streaming ingest (`proto/`), API tests |
| `ai_core/common/` | Settings, strict Pydantic contracts, event-bus & state abstractions (Kafka/Redis ↔ in-memory), DI container |
| `ai_core/vision/` | `HybridSpatialNet` (EfficientNet-V2 + ViT, 4-channel optical+thermal), TensorRT/ONNX path, FedAvg + clipping/DP noise, edge service, simulator |
| `ai_core/rag/` | Semantic chunker, embedders, pgvector store, **temporal Neo4j graph**, hybrid retriever + cross-encoder rerank, ingestion worker, seed manuals |
| `ai_core/agents/` | LangGraph swarm: allow-listed action catalog, deterministic nodes, checkpointing, HITL resume |
| `security/` | Hybrid **X25519 + ML-KEM-768** envelope encryption (AES-256-GCM); Ed25519/HMAC approval gate with nonce + replay protection |
| `infra/` | Docker (CPU + GPU), Prometheus, Grafana (provisioned), OTel collector, Jaeger, **Helm chart** |
| `scripts/` | `e2e_test.py`, `sign_approval.py`, `smoke.sh` |

## Quick start (full cluster)
```bash
cp .env.example .env            # then change every "change-me-*" value
docker compose up -d --build    # first build takes a few minutes
python scripts/e2e_test.py      # end-to-end: anomaly → swarm → forged approval rejected → signed approval → remediation
```
| Service | URL |
|---|---|
| 3D twin UI | http://localhost:3000 |
| API docs | http://localhost:8000/docs (send `X-API-Key`) |
| Grafana | http://localhost:3001 (admin / `GRAFANA_ADMIN_PASSWORD`) |
| Prometheus · Jaeger · Neo4j | :9090 · :16686 · :7474 |

Open the UI, click **inject test anomaly**: the node pulses, the swarm trace streams into the inspector drawer, and an approval card appears
(bottom-left). Enter the approver token from `APPROVER_TOKENS` and approve.

**GPU edge inference** (NVIDIA Container Toolkit, weights in `./models/hybrid_spatialnet.pt`):
`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`

**No-Docker demo** (single process, in-memory bus/state/vector/graph): `make lite`, then `cd frontend && npm i && npm run dev`.

## Configuration (`.env.example` is authoritative)
Key variables: `KAFKA_BOOTSTRAP`, `REDIS_URL`/`REDIS_CLUSTER`, `POSTGRES_DSN`, `NEO4J_*`, `EMBEDDING_BACKEND` (`hashing`|`sentence-transformers`),
`RERANK_BACKEND` (`lexical`|`cross-encoder`), `MIN_EVIDENCE_SCORE`, `HITL_RISK_THRESHOLD`, `APPROVAL_MODE` (`token`|`ed25519`),
`VISION_BACKEND` (`simulated`|`torch`), `RTSP_URLS` (`N-01=rtsp://…,N-02=…`), `OTEL_ENDPOINT`, `PQ_REQUIRED`.

## Security setup
1. **Secrets**: replace all `change-me-*`. Never ship `.env`; in Kubernetes use the Secret referenced by `existingSecret`.
2. **API auth**: REST uses `X-API-Key`, WebSocket uses `?key=`. The bundled UI embeds a key at build time — fine for a lab, **not** for production. Put the API behind your gateway/OIDC and issue per-user tokens.
3. **Human approvals** (anything `physical=true` or risk ≥ `HITL_RISK_THRESHOLD`):
   - `token` mode (default): approver credential is verified by the API and converted to an HMAC attestation; the credential never reaches the event bus.
   - `ed25519` mode (recommended for production): `make keys` → register the **public** key in `APPROVER_PUBKEYS=name:<hex>`; approvers sign offline with `scripts/sign_approval.py sign …` and POST `{"signature": …}`.
   - Every request carries a one-time **nonce** + expiry; the worker re-verifies the attestation independently and records consumed nonces (replay → refused).
4. **Post-quantum transport**: `security/pq.py` seals telemetry with X25519 **+ ML-KEM-768** (hybrid; secure if either holds). ML-KEM needs `liboqs-python`; without it the envelope falls back to X25519-only and is labelled `pq:false`. Set `PQ_REQUIRED=true` to refuse that downgrade.
5. **Network**: gRPC listens plaintext on :50051 — terminate mTLS at your mesh/ingress. Do not expose Redpanda/Redis/Postgres/Neo4j publicly (compose only publishes the Kafka external listener and Neo4j browser for development; remove in prod).

## How the "zero-hallucination" guarantee works
- No generative model sits in the action path. Agents are deterministic functions over typed state.
- `Compliance RAG` returns evidence only above `MIN_EVIDENCE_SCORE` after reranking; **no evidence → the swarm abstains and escalates**.
- The planner may only choose from `ai_core/agents/catalog.py` (allow-list with numeric bounds). An action is permitted only if a retrieved manual passage mentions it; citations are attached to the plan.
- The verifier re-checks bounds, evidence and a dry-run simulation; failures loop back to the planner for programmatic correction (e.g. clamping 96 % → 90 %), otherwise escalate.
- After a human approves, the plan is **re-verified** before execution (the world may have changed while waiting).

## Testing
```bash
make test                  # pytest: security, federated learning, chunking, swarm (self-correction, HITL, replay, abstention), API
python scripts/e2e_test.py # against a running stack
scripts/smoke.sh           # health / readiness / metrics
cd frontend && npm run typecheck && npm run build
```

## Kubernetes
```bash
helm upgrade --install aether infra/helm/corona -n aether --create-namespace \
  --set image.registry=<your-registry> --set image.tag=<tag>
```
The chart deploys api / worker / edge / frontend, a ConfigMap, optional Ingress, and expects managed Redpanda/Kafka, Redis Cluster, Postgres+pgvector and Neo4j (see `values.yaml`).

## Honest status — what is production-grade vs. what you must supply
| Area | State |
|---|---|
| Architecture, contracts, swarm logic, HITL crypto, bus/state abstractions, Compose/Helm, UI | Complete and wired end-to-end |
| Vision model | `HybridSpatialNet` + inference/ONNX/TensorRT code are included, **but no trained weights**. Default `VISION_BACKEND=simulated` produces physically-plausible faults so the whole loop runs. Train on your labelled thermal/optical data, drop weights at `VISION_WEIGHTS`, set `VISION_BACKEND=torch`. |
| Federated learning | FedAvg + clipping + optional Gaussian noise and a bus-driven coordinator are included; the demo clients send synthetic deltas. Real clients must submit weight deltas from local training. |
| "Compute shaders" | Heat field and node shading run as GLSL **fragment-shader passes** (WebGL2, works everywhere). A WebGPU/TSL compute-shader port is the next step if you need >10⁵ emitters. |
| Embeddings / rerank | Defaults are dependency-free (`hashing`, `lexical`) so CI is hermetic. Switch to `sentence-transformers` + `cross-encoder` for production retrieval quality. |
| Actuation | `Executor` publishes `remediation.executed` and writes to the graph; wiring to real PLC/SCADA/OT systems is deliberately left to you. |
| Scale | pgvector access uses a connection per call; add a pool (`psycopg_pool`) and partition keys for high throughput. LangGraph is checkpointed via the state store; swap in `langgraph-checkpoint-postgres` if you prefer its saver. |
| Validation | Logic was exercised in a sandbox without Docker/Kafka/GPU. Run `make test` and `scripts/e2e_test.py` in your environment before relying on it. |
