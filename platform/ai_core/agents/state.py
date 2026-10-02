from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class SwarmState(TypedDict, total=False):
    thread_id: str
    anomaly: dict[str, Any]
    attempt: int
    validation: dict[str, Any]
    evidence: list[dict[str, Any]]
    graph_context: dict[str, Any]
    risk: float
    risk_factors: dict[str, float]
    plan: dict[str, Any]
    revisions: int
    corrections: list[str]
    verification: dict[str, Any]
    approval: dict[str, Any]
    status: str
    trace: Annotated[list[dict[str, Any]], operator.add]
