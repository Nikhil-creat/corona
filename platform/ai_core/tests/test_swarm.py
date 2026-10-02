import pytest

from ai_core.agents.graph import SwarmRunner
from ai_core.common.container import build_container, seed_topology
from ai_core.common.schemas import AnomalyEvent, ApprovalDecision, ApprovalRequest, TelemetryPacket


def _anomaly(node="N-01", label="thermal_overheat", sev=0.8, conf=0.93, temp=112.0):
    tel = TelemetryPacket(node_id=node, temperature_c=temp, vibration_mm_s=3, stress_pct=40)
    mod = {"thermal_overheat": "thermal", "bearing_wear": "optical"}[label]
    return AnomalyEvent(node_id=node, modality=mod, label=label, severity=sev, confidence=conf, telemetry=tel)


@pytest.fixture
async def runner():
    c = await build_container()
    await seed_topology(c.graph)
    await c.pipeline.seed_if_empty()
    return SwarmRunner(c)


async def test_self_correction_then_human_approval_and_replay_protection(runner):
    a = _anomaly()
    final = await runner.run(a)
    assert final["status"] == "awaiting_approval"
    assert final["plan"]["params"]["percent"] == 90  # naive 96 → rejected by verifier → clamped
    assert any("outside permitted range" in t["message"] for t in final["trace"])
    req = ApprovalRequest(**final["approval"])
    c = runner.c
    att = c.verifier.authenticate(a.id, req.nonce, True, "ops-lead", "dev-approver-token", None)
    d = ApprovalDecision(thread_id=a.id, approve=True, approver="ops-lead", nonce=req.nonce, signature=att)
    assert (await runner.resume(d))["status"] == "remediated"
    assert await runner.resume(d) is None  # replay refused


async def test_forged_attestation_is_refused(runner):
    a = _anomaly(node="N-02")
    final = await runner.run(a)
    req = ApprovalRequest(**final["approval"])
    d = ApprovalDecision(thread_id=a.id, approve=True, approver="ops-lead", nonce=req.nonce, signature="hmac:deadbeef")
    assert await runner.resume(d) is None
    cp = await runner.c.state.get(f"swarm:{a.id}:checkpoint")
    assert cp["status"] == "awaiting_approval"


async def test_false_positive_is_closed(runner):
    a = _anomaly(node="N-05", label="bearing_wear", sev=0.3, conf=0.6, temp=55)
    assert (await runner.run(a))["status"] == "rejected_false_positive"


async def test_abstains_without_evidence(runner):
    runner.c.store._rows.clear()
    assert (await runner.run(_anomaly(node="N-03")))["status"] == "escalated_no_evidence"
