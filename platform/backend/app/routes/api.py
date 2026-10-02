from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ai_core.common.container import Container
from ai_core.common.ingest import ingest_anomaly, ingest_telemetry
from ai_core.common.schemas import AnomalyEvent, ApprovalDecision, ApprovalRequest, Detection, TelemetryPacket
from ai_core.common.topics import Topics
from ai_core.common.topology import EDGES, NODE_IDS, NODES
from security.approvals import ApprovalError

from ..deps import get_container, require_api_key

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


@router.get("/topology")
async def topology() -> dict[str, Any]:
    return {"nodes": NODES, "edges": EDGES}


@router.get("/nodes")
async def nodes(c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    out = []
    for nid in NODE_IDS:
        latest = await c.state.get(f"node:{nid}:latest")
        if latest:
            out.append(latest)
    return out


@router.post("/telemetry", status_code=202)
async def post_telemetry(packet: TelemetryPacket, c: Container = Depends(get_container)) -> dict[str, str]:
    if packet.node_id not in NODE_IDS:
        raise HTTPException(404, "unknown node")
    await ingest_telemetry(c, packet)
    return {"status": "accepted"}


@router.get("/anomalies")
async def anomalies(limit: int = 50, c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    return await c.state.lrange("anomalies:recent", 0, min(limit, 100) - 1)


@router.get("/swarm/{thread_id}/trace")
async def trace(thread_id: str, c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    return list(reversed(await c.state.lrange(f"swarm:{thread_id}:trace", 0, 199)))


@router.get("/swarm/{thread_id}")
async def checkpoint(thread_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    cp = await c.state.get(f"swarm:{thread_id}:checkpoint")
    if not cp:
        raise HTTPException(404, "unknown thread")
    return cp


# ── Human-in-the-loop approvals ─────────────────────────────────────────
@router.get("/approvals/pending")
async def pending(c: Container = Depends(get_container)) -> list[dict[str, Any]]:
    keys = await c.state.keys("approval:")
    docs = [await c.state.get(k) for k in keys]
    return sorted((d for d in docs if d), key=lambda d: d["created_at"])


class DecisionIn(BaseModel):
    approve: bool
    approver: str = Field(min_length=1, max_length=64)
    nonce: str
    token: str | None = None
    signature: str | None = None


@router.post("/approvals/{thread_id}/decision", status_code=202)
async def decide(thread_id: str, body: DecisionIn, c: Container = Depends(get_container)) -> dict[str, str]:
    raw = await c.state.get(f"approval:{thread_id}")
    if not raw:
        raise HTTPException(404, "no pending approval for this thread")
    req = ApprovalRequest(**raw)
    if body.nonce != req.nonce or time.time() > req.expires_at:
        raise HTTPException(409, "stale approval request")
    try:
        attestation = c.verifier.authenticate(thread_id, body.nonce, body.approve, body.approver, body.token, body.signature)
    except ApprovalError as exc:
        raise HTTPException(403, str(exc)) from exc
    decision = ApprovalDecision(thread_id=thread_id, approve=body.approve, approver=body.approver, nonce=body.nonce, signature=attestation)
    await c.bus.publish(Topics.APPROVAL_DECISIONS, decision, key=thread_id)  # credentials never hit the bus
    return {"status": "queued"}


# ── Knowledge fabric ────────────────────────────────────────────────────
class QueryIn(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    top_n: int = Field(default=4, ge=1, le=10)


@router.post("/rag/query")
async def rag_query(body: QueryIn, c: Container = Depends(get_container)) -> dict[str, Any]:
    ev = await c.retriever.retrieve(body.query, top_n=body.top_n)
    return {"abstained": not ev, "evidence": [e.__dict__ for e in ev]}


@router.post("/rag/ingest", status_code=201)
async def rag_ingest(file: UploadFile = File(...), c: Container = Depends(get_container)) -> dict[str, Any]:
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "doc.txt").suffix.lower()
    if suffix not in {".pdf", ".md", ".txt", ".json"}:
        raise HTTPException(415, "unsupported file type")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "file too large")
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / Path(file.filename or "doc.txt").name
        p.write_bytes(data)
        n = await c.pipeline.ingest_file(p)
    return {"chunks": n}


@router.get("/graph/{node_id}")
async def graph_context(node_id: str, c: Container = Depends(get_container)) -> dict[str, Any]:
    if node_id not in NODE_IDS:
        raise HTTPException(404, "unknown node")
    return await c.graph.context(node_id)


# ── Dev helper (disabled outside ENV=dev|test) ──────────────────────────
class InjectIn(BaseModel):
    node_id: str = "N-01"
    label: str = "thermal_overheat"
    severity: float = Field(default=0.8, ge=0, le=1)


@router.post("/dev/inject-anomaly", status_code=202)
async def inject(body: InjectIn, c: Container = Depends(get_container)) -> dict[str, str]:
    if c.settings.env not in ("dev", "test"):
        raise HTTPException(404)
    from ai_core.vision.labels import MODALITY

    if body.label not in MODALITY or body.node_id not in NODE_IDS:
        raise HTTPException(422, "unknown label or node")
    hot = {"thermal_overheat": (112, 3, 40), "electrical_fault": (101, 3, 40), "bearing_wear": (70, 9, 40), "structural_crack": (60, 5, 85)}[body.label]
    tel = TelemetryPacket(node_id=body.node_id, temperature_c=hot[0], vibration_mm_s=hot[1] if body.label != "bearing_wear" else hot[1], stress_pct=hot[2])
    event = AnomalyEvent(id=uuid.uuid4().hex, node_id=body.node_id, modality=MODALITY[body.label], label=body.label,  # type: ignore[arg-type]
                         severity=body.severity, confidence=0.93, telemetry=tel,
                         detections=[Detection(label=body.label, confidence=0.93, bbox=(0.3, 0.3, 0.3, 0.25))])
    await ingest_telemetry(c, tel)
    await ingest_anomaly(c, event)
    return {"thread_id": event.id}
