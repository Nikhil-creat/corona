#!/usr/bin/env python3
"""End-to-end check against a running stack: inject anomaly → swarm → HITL approval → remediation."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.getenv("API_URL", "http://localhost:8000")
KEY = os.getenv("API_KEY", os.getenv("API_KEYS", "change-me-api-key").split(",")[0])
APPROVER = os.getenv("APPROVER", "ops-lead")
TOKEN = os.getenv("APPROVER_TOKEN", os.getenv("APPROVER_TOKENS", "ops-lead:change-me-approver-token").split(",")[0].split(":", 1)[1])


def call(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(f"{API}{path}", method=method, headers={"X-API-Key": KEY, "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def wait(fn, what: str, timeout: float = 90):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(1)
    sys.exit(f"✗ timed out waiting for {what}")


def main() -> None:
    def ready():
        try:
            return call("GET", "/readyz")[0] == 200
        except OSError:
            return False

    wait(ready, "API ready")
    print("✓ API ready")
    code, body = call("POST", "/api/rag/query", {"query": "thermal overheat throttle load"})
    assert code == 200 and not body["abstained"], f"RAG not grounded: {body}"
    print(f"✓ RAG grounded ({len(body['evidence'])} passages)")
    code, body = call("POST", "/api/dev/inject-anomaly", {"node_id": "N-01", "label": "thermal_overheat", "severity": 0.8})
    assert code == 202, body
    tid = body["thread_id"]
    req = wait(lambda: next((a for a in call("GET", "/api/approvals/pending")[1] if a["thread_id"] == tid), None), "approval request")
    print(f"✓ swarm produced plan: {req['plan']['action']} {req['plan']['params']} (risk {req['risk']:.2f})")
    code, _ = call("POST", f"/api/approvals/{tid}/decision", {"approve": True, "approver": APPROVER, "nonce": req["nonce"], "token": "definitely-wrong"})
    assert code == 403, "bad credentials must be rejected"
    print("✓ forged approval rejected")
    code, _ = call("POST", f"/api/approvals/{tid}/decision", {"approve": True, "approver": APPROVER, "nonce": req["nonce"], "token": TOKEN})
    assert code == 202
    wait(lambda: call("GET", f"/api/swarm/{tid}")[1].get("status") == "remediated", "remediation")
    print("✓ remediation executed after signed approval")
    trace = call("GET", f"/api/swarm/{tid}/trace")[1]
    print("  agents:", " → ".join(dict.fromkeys(e["agent"] for e in trace)))
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
