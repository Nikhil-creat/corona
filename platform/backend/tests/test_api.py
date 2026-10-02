import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

H = {"X-API-Key": "dev-api-key"}


def wait_for(fn, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError("timed out")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_auth_required(client):
    assert client.get("/api/topology").status_code == 401
    assert client.get("/healthz").status_code == 200


def test_rag_grounded_and_abstains(client):
    ok = client.post("/api/rag/query", json={"query": "thermal overheat throttle load response"}, headers=H).json()
    assert not ok["abstained"] and ok["evidence"]
    none = client.post("/api/rag/query", json={"query": "zzqx wibble frobnicate"}, headers=H).json()
    assert none["abstained"]


def test_full_swarm_with_human_approval(client):
    tid = client.post("/api/dev/inject-anomaly", json={"node_id": "N-01", "label": "thermal_overheat", "severity": 0.8}, headers=H).json()["thread_id"]
    req = wait_for(lambda: next((a for a in client.get("/api/approvals/pending", headers=H).json() if a["thread_id"] == tid), None))
    assert req["plan"]["action"] == "throttle_load" and req["plan"]["params"]["percent"] == 90  # clamped by verifier loop
    bad = client.post(f"/api/approvals/{tid}/decision", headers=H, json={"approve": True, "approver": "ops-lead", "nonce": req["nonce"], "token": "nope"})
    assert bad.status_code == 403
    good = client.post(f"/api/approvals/{tid}/decision", headers=H, json={"approve": True, "approver": "ops-lead", "nonce": req["nonce"], "token": "dev-approver-token"})
    assert good.status_code == 202
    cp = wait_for(lambda: (lambda d: d if d.get("status") == "remediated" else None)(client.get(f"/api/swarm/{tid}", headers=H).json()))
    assert cp["approval"]["approved_by"] == "ops-lead"
    assert any(e["agent"] == "Fix Verification" for e in client.get(f"/api/swarm/{tid}/trace", headers=H).json())
