"""Agent nodes. Every node is deterministic: same state in → same state out (no sampling, no network LLM).
An LLM can be slotted into `planner` for *drafting rationale only*; the verifier still gates every action."""
from __future__ import annotations

import time
import uuid
from typing import Any

from ai_core.common.container import Container
from ai_core.common.schemas import AnomalyEvent, ApprovalRequest, RemediationPlan, SwarmEvent, TelemetryPacket
from ai_core.common.topics import Topics

from .catalog import ACTIONS, clamp, propose
from .state import SwarmState

Update = dict[str, Any]


async def emit(c: Container, s: SwarmState, agent: str, kind: str, message: str, **data: Any) -> dict[str, Any]:
    ev = SwarmEvent(thread_id=s["thread_id"], node_id=s["anomaly"]["node_id"], agent=agent, kind=kind, message=message, data=data)  # type: ignore[arg-type]
    doc = ev.model_dump(mode="json")
    await c.state.lpush_trim(f"swarm:{ev.thread_id}:trace", doc, 200)
    await c.bus.publish(Topics.SWARM_EVENTS, ev, key=ev.thread_id)
    return doc


def _corroborated(modality: str, tel: TelemetryPacket | None) -> bool:
    if tel is None:
        return False
    return {"thermal": tel.temperature_c >= 85, "structural": tel.stress_pct >= 70, "optical": tel.vibration_mm_s >= 6}.get(modality, False)


# 1 ─ Validator (with self-reflection loop) ────────────────────────────────────────────
async def validator(c: Container, s: SwarmState) -> Update:
    a = AnomalyEvent(**s["anomaly"])
    attempt = s.get("attempt", 0)
    tel = a.telemetry
    if attempt > 0:  # reflection: re-read the freshest telemetry before deciding again
        latest = await c.state.get(f"node:{a.node_id}:latest")
        tel = TelemetryPacket(**latest) if latest else tel
    hist = await c.state.lrange(f"anomalies:{a.node_id}", 0, 19)
    recurrence = sum(1 for h in hist if h["label"] == a.label and h["id"] != a.id and a.ts - h["ts"] < 600)
    corroborated = _corroborated(a.modality, tel)

    if a.confidence < 0.5:
        verdict, why = "reject", f"confidence {a.confidence:.2f} below 0.50 floor"
    elif corroborated or a.confidence >= 0.85 or recurrence >= 2:
        verdict = "ok"
        why = f"confidence {a.confidence:.2f}, sensor corroboration={corroborated}, recurrence={recurrence}"
    elif attempt < 2:
        verdict, why = "retry", f"inconclusive (attempt {attempt + 1}/3) — re-reading telemetry"
    else:
        verdict, why = "reject", "still uncorroborated after reflection; treated as false positive"

    entry = await emit(c, s, "Validator", "thought" if verdict == "retry" else "result", why, verdict=verdict)
    out: Update = {"validation": {"verdict": verdict, "reason": why}, "trace": [entry]}
    if verdict == "retry":
        out["attempt"] = attempt + 1
    elif verdict == "reject":
        out["status"] = "rejected_false_positive"
        out["trace"].append(await emit(c, s, "Validator", "status", "closed as false positive", status="false_positive"))
    else:
        out["trace"].append(await emit(c, s, "Validator", "status", "investigating", status="investigating"))
        out["status"] = "investigating"
    return out


# 2 ─ Compliance RAG agent ─────────────────────────────────────────────────────────────
async def compliance(c: Container, s: SwarmState) -> Update:
    a = AnomalyEvent(**s["anomaly"])
    query = f"{a.label.replace('_', ' ')} {a.modality} anomaly response procedure approved action limits"
    evidence = await c.retriever.retrieve(query)
    gctx = await c.graph.context(a.node_id)
    if not evidence:
        e1 = await emit(c, s, "Compliance RAG", "escalation",
                        "No authoritative evidence above threshold — abstaining and escalating to a human.", status="escalated")
        return {"status": "escalated_no_evidence", "evidence": [], "graph_context": gctx, "trace": [e1]}
    docs = ", ".join(sorted({e.source for e in evidence}))
    e1 = await emit(c, s, "Compliance RAG", "result", f"{len(evidence)} authoritative passages retrieved from: {docs}",
                    sources=[e.source for e in evidence])
    return {"evidence": [e.__dict__ for e in evidence], "graph_context": gctx, "trace": [e1]}


# 3 ─ Risk assessment ──────────────────────────────────────────────────────────────────
async def risk(c: Container, s: SwarmState) -> Update:
    a, g = AnomalyEvent(**s["anomaly"]), s["graph_context"]
    factors = {
        "severity": 0.45 * a.severity,
        "confidence": 0.15 * a.confidence,
        "criticality_and_blast_radius": 0.20 * (0.5 * g["criticality"] + 0.5 * min(len(g["dependents"]) / 5, 1)),
        "component_age": 0.10 * min(g["age_days"] / 3650, 1),
        "recent_failures": 0.10 * min(g["failures_90d"] / 3, 1),
    }
    score = round(sum(factors.values()), 4)
    e1 = await emit(c, s, "Risk Assessment", "result",
                    f"risk={score:.2f} (dependents: {', '.join(g['dependents']) or 'none'}; failures/90d: {g['failures_90d']})",
                    risk=score, factors={k: round(v, 3) for k, v in factors.items()})
    return {"risk": score, "risk_factors": factors, "trace": [e1]}


# 4 ─ Remediation planner ──────────────────────────────────────────────────────────────
async def planner(c: Container, s: SwarmState) -> Update:
    a = AnomalyEvent(**s["anomaly"])
    revisions = s.get("revisions", 0)
    revising = bool(s.get("corrections"))
    if not revising:
        action, params = propose(a.label, a.severity)
    else:  # programmatic error correction: clamp the previous proposal into verified bounds
        prev = s["plan"]
        action, params = prev["action"], clamp(prev["action"], prev["params"])
    spec = ACTIONS[action]
    cites = [e["chunk_id"] for e in s["evidence"] if spec.evidence_keyword in e["text"].lower()]
    plan = RemediationPlan(
        action=action, params=params, physical=spec.physical, citations=cites,
        rationale=f"{spec.description} for {a.label} (severity {a.severity:.2f}); grounded in {len(cites)} manual passage(s).",
    )
    note = "revised after verification feedback" if revising else "initial proposal"
    e1 = await emit(c, s, "Remediation Planner", "thought", f"{action} {params} — {note}", plan=plan.model_dump())
    return {"plan": plan.model_dump(), "revisions": revisions + (1 if revising else 0), "trace": [e1]}


# 5 ─ Fix verification (dry-run simulation + bounds + evidence) ────────────────────────
def verify_plan(plan: dict[str, Any], anomaly: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    spec = ACTIONS.get(plan["action"])
    if spec is None:
        return {"passed": False, "violations": [f"action {plan['action']} not in allow-list"], "simulation": {}, "fixable": False}
    for key, (lo, hi) in spec.bounds.items():
        v = plan["params"].get(key)
        if v is None or not lo <= v <= hi:
            violations.append(f"{key}={v} outside permitted range [{lo}, {hi}]")
    fixable = True
    if not plan["citations"]:
        violations.append("no supporting evidence for action")
        fixable = False
    tel = anomaly.get("telemetry") or {}
    sim: dict[str, Any] = {}
    if plan["action"] == "throttle_load" and "percent" in plan["params"]:
        sim["predicted_temperature_c"] = round(tel.get("temperature_c", 90) - 0.45 * plan["params"]["percent"], 1)
        if sim["predicted_temperature_c"] >= 85:
            violations.append("simulation: throttle insufficient to return below 85°C")
            fixable = False
    if plan["action"] == "schedule_inspection" and anomaly["severity"] >= 0.7:
        violations.append("simulation: inspection alone is insufficient for severity ≥ 0.70")
        fixable = False
    return {"passed": not violations, "violations": violations, "simulation": sim, "fixable": fixable}


async def verifier(c: Container, s: SwarmState) -> Update:
    result = verify_plan(s["plan"], s["anomaly"])
    msg = "plan verified (bounds ✓ evidence ✓ dry-run ✓)" if result["passed"] else "; ".join(result["violations"])
    e1 = await emit(c, s, "Fix Verification", "result" if result["passed"] else "thought", msg, passed=result["passed"], simulation=result["simulation"])
    out: Update = {"verification": result, "corrections": result["violations"], "trace": [e1]}
    if not result["passed"] and (not result["fixable"] or s.get("revisions", 0) >= 2):
        out["status"] = "escalated_unverifiable"
        out["trace"].append(await emit(c, s, "Fix Verification", "escalation", "Plan cannot be verified automatically — human review required.", status="escalated"))
    return out


# 6 ─ HITL gate ────────────────────────────────────────────────────────────────────────
async def gate(c: Container, s: SwarmState) -> Update:
    plan = RemediationPlan(**s["plan"])
    needs = s["risk"] >= c.settings.hitl_risk_threshold or plan.physical
    if not needs:
        return {"status": "auto_approved", "trace": [await emit(c, s, "HITL Gate", "result", "low risk, non-physical → auto-approved")]}
    now = time.time()
    req = ApprovalRequest(thread_id=s["thread_id"], node_id=s["anomaly"]["node_id"], plan=plan, risk=s["risk"],
                          nonce=uuid.uuid4().hex, created_at=now, expires_at=now + c.settings.approval_ttl_s)
    await c.state.set(f"approval:{req.thread_id}", req.model_dump(mode="json"), ttl=c.settings.approval_ttl_s)
    await c.bus.publish(Topics.APPROVAL_REQUESTS, req, key=req.thread_id)
    e1 = await emit(c, s, "HITL Gate", "escalation", f"Awaiting signed human approval for {plan.action} (risk {s['risk']:.2f})", status="awaiting_approval")
    return {"status": "awaiting_approval", "approval": req.model_dump(mode="json"), "trace": [e1]}


# 7 ─ Execute ──────────────────────────────────────────────────────────────────────────
async def execute(c: Container, s: SwarmState) -> Update:
    node, plan = s["anomaly"]["node_id"], s["plan"]
    now = time.time()
    await c.bus.publish(Topics.REMEDIATION, {"thread_id": s["thread_id"], "node_id": node, "plan": plan, "ts": now,
                                             "approver": (s.get("approval") or {}).get("approved_by")})
    await c.graph.record_event(node, f"remediation:{plan['action']}", now, {"thread": s["thread_id"], "params": plan["params"]})
    if s["anomaly"]["severity"] >= 0.6:
        await c.graph.record_event(node, f"failure:{s['anomaly']['label']}", now, {"thread": s["thread_id"]})
    e1 = await emit(c, s, "Executor", "status", f"{plan['action']} dispatched to actuator layer (simulated)", status="remediated")
    return {"status": "remediated", "trace": [e1]}


# ── routing ──
def route_validator(s: SwarmState) -> str:
    return s["validation"]["verdict"]


def route_compliance(s: SwarmState) -> str:
    return "ok" if s.get("evidence") else "escalate"


def route_verifier(s: SwarmState) -> str:
    v = s["verification"]
    if v["passed"]:
        return "ok"
    return "escalate" if s.get("status", "").startswith("escalated") else "revise"


def route_gate(s: SwarmState) -> str:
    return "approval" if s.get("status") == "awaiting_approval" else "auto"
