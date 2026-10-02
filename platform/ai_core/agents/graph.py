"""LangGraph swarm definition + durable checkpointing + HITL resume.

The graph topology lives in plain dicts so the SAME definition drives (a) LangGraph when installed and
(b) a tiny built-in executor (dev / CI). Every node transition is checkpointed to the state store so a worker
crash can resume, and so the human-approval gate can pause for minutes or days."""
from __future__ import annotations

import logging
from typing import Any

from ai_core.common.container import Container
from ai_core.common.schemas import ApprovalDecision, ApprovalRequest, AnomalyEvent
from security.approvals import ApprovalError

from . import nodes
from .state import SwarmState

log = logging.getLogger(__name__)
END = "__end__"
ENTRY = "validator"

NODES = {
    "validator": nodes.validator, "compliance": nodes.compliance, "risk": nodes.risk, "planner": nodes.planner,
    "verifier": nodes.verifier, "gate": nodes.gate, "execute": nodes.execute,
}
EDGES = {"risk": "planner", "planner": "verifier", "execute": END}
ROUTES = {
    "validator": (nodes.route_validator, {"ok": "compliance", "retry": "validator", "reject": END}),
    "compliance": (nodes.route_compliance, {"ok": "risk", "escalate": END}),
    "verifier": (nodes.route_verifier, {"ok": "gate", "revise": "planner", "escalate": END}),
    "gate": (nodes.route_gate, {"approval": END, "auto": "execute"}),
}


def _merge(state: SwarmState, out: dict[str, Any]) -> SwarmState:
    merged: dict[str, Any] = {**state, **{k: v for k, v in out.items() if k != "trace"}}
    merged["trace"] = list(state.get("trace", [])) + list(out.get("trace", []))
    return merged  # type: ignore[return-value]


class SwarmRunner:
    def __init__(self, c: Container) -> None:
        self.c = c
        self._lg = self._build_langgraph()

    # ── execution ─────────────────────────────────────────────
    def _wrap(self, name: str):
        async def step(state: SwarmState) -> dict[str, Any]:
            out = await NODES[name](self.c, state)
            await self.c.state.set(f"swarm:{state['thread_id']}:checkpoint", _merge(state, out), ttl=7 * 86400)
            return out
        return step

    def _build_langgraph(self):
        try:
            from langgraph.graph import END as LG_END, StateGraph
        except ImportError:
            log.info("langgraph not installed — using built-in executor")
            return None
        g = StateGraph(SwarmState)
        for name in NODES:
            g.add_node(name, self._wrap(name))
        g.set_entry_point(ENTRY)
        for src, dst in EDGES.items():
            g.add_edge(src, LG_END if dst == END else dst)
        for src, (fn, branches) in ROUTES.items():
            g.add_conditional_edges(src, fn, {k: (LG_END if v == END else v) for k, v in branches.items()})
        return g.compile()

    async def _run_builtin(self, state: SwarmState, start: str) -> SwarmState:
        node = start
        while node != END:
            state = _merge(state, await self._wrap(node)(state))
            if node in ROUTES:
                fn, branches = ROUTES[node]
                node = branches[fn(state)]
            else:
                node = EDGES[node]
        return state

    async def run(self, anomaly: AnomalyEvent) -> SwarmState:
        state: SwarmState = {"thread_id": anomaly.id, "anomaly": anomaly.model_dump(mode="json"), "attempt": 0,
                             "revisions": 0, "status": "started", "trace": []}
        try:
            if self._lg is not None:
                return await self._lg.ainvoke(state, {"recursion_limit": 40})
            return await self._run_builtin(state, ENTRY)
        except Exception as exc:  # isolation: one failing thread must never affect the swarm
            log.exception("swarm thread %s failed", anomaly.id)
            await nodes.emit(self.c, state, "Supervisor", "escalation", f"agent thread crashed: {exc!r}", status="escalated")
            await self.c.state.set(f"swarm:{anomaly.id}:checkpoint", {**state, "status": "failed"}, ttl=86400)
            return {**state, "status": "failed"}  # type: ignore[return-value]

    # ── HITL resume ───────────────────────────────────────────
    async def resume(self, d: ApprovalDecision) -> SwarmState | None:
        cp: SwarmState | None = await self.c.state.get(f"swarm:{d.thread_id}:checkpoint")
        if not cp or cp.get("status") != "awaiting_approval":
            return None
        req = ApprovalRequest(**cp["approval"])

        async def refuse(reason: str) -> None:
            await nodes.emit(self.c, cp, "HITL Gate", "escalation", f"decision refused: {reason}", status="awaiting_approval")

        import time
        if d.nonce != req.nonce or time.time() > req.expires_at:
            await refuse("stale or mismatched nonce")
            return None
        try:
            self.c.verifier.verify_attested(d.thread_id, d.nonce, d.approve, d.approver, d.signature or "")
        except ApprovalError as exc:
            await refuse(str(exc))
            return None
        if not await self.c.state.set_if_absent(f"nonce:{req.nonce}", 1, ttl=self.c.settings.approval_ttl_s * 2):
            await refuse("replay detected")
            return None
        await self.c.state.delete(f"approval:{d.thread_id}")

        if not d.approve:
            e = await nodes.emit(self.c, cp, "HITL Gate", "status", f"rejected by {d.approver}", status="rejected_by_human")
            final = _merge(cp, {"status": "rejected_by_human", "trace": [e]})
            await self.c.state.set(f"swarm:{d.thread_id}:checkpoint", final, ttl=7 * 86400)
            return final
        e = await nodes.emit(self.c, cp, "HITL Gate", "result", f"approved by {d.approver} (signature verified)")
        cp = _merge(cp, {"approval": {**cp["approval"], "approved_by": d.approver}, "trace": [e]})
        recheck = nodes.verify_plan(cp["plan"], cp["anomaly"])  # world may have changed while waiting
        if not recheck["passed"]:
            e2 = await nodes.emit(self.c, cp, "Fix Verification", "escalation", "re-verification failed after approval: " + "; ".join(recheck["violations"]), status="escalated")
            final = _merge(cp, {"status": "escalated_unverifiable", "trace": [e2]})
        else:
            final = await self._run_builtin(cp, "execute")
        await self.c.state.set(f"swarm:{d.thread_id}:checkpoint", final, ttl=7 * 86400)
        return final
