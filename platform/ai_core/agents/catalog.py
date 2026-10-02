"""Allow-listed remediation actions with hard parameter bounds. The swarm can only ever emit these."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ActionSpec:
    physical: bool
    bounds: dict[str, tuple[float, float]]
    evidence_keyword: str  # a retrieved manual chunk must mention this before the action is allowed
    description: str = ""


ACTIONS: dict[str, ActionSpec] = {
    "throttle_load": ActionSpec(False, {"percent": (10, 90)}, "throttle", "Reduce sustained load on node"),
    "schedule_inspection": ActionSpec(False, {"within_hours": (1, 168)}, "inspection", "Schedule technician inspection"),
    "isolate_node": ActionSpec(True, {"grace_s": (0, 300)}, "isolate", "Remove node from active routing"),
    "emergency_shutdown": ActionSpec(True, {"grace_s": (0, 60)}, "shutdown", "Controlled emergency shutdown"),
}

Proposal = tuple[str, dict[str, float]]


def _thermal(sev: float) -> Proposal:
    if sev > 0.9:
        return "emergency_shutdown", {"grace_s": 30}
    return "throttle_load", {"percent": round(40 + sev * 70)}  # deliberately naive; verifier enforces bounds


def _bearing(sev: float) -> Proposal:
    return ("isolate_node", {"grace_s": 60}) if sev > 0.7 else ("schedule_inspection", {"within_hours": round(72 - sev * 60)})


def _structural(sev: float) -> Proposal:
    return ("isolate_node", {"grace_s": 30}) if sev > 0.6 else ("schedule_inspection", {"within_hours": 12})


POLICY: dict[str, Callable[[float], Proposal]] = {
    "thermal_overheat": _thermal,
    "bearing_wear": _bearing,
    "structural_crack": _structural,
    "electrical_fault": lambda sev: ("isolate_node", {"grace_s": 15}),
}


def propose(label: str, severity: float) -> Proposal:
    return POLICY.get(label, lambda s: ("schedule_inspection", {"within_hours": 24}))(severity)


def clamp(action: str, params: dict[str, float]) -> dict[str, float]:
    spec = ACTIONS[action]
    return {k: min(max(v, spec.bounds[k][0]), spec.bounds[k][1]) if k in spec.bounds else v for k, v in params.items()}
