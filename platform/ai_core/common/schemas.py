"""Strictly validated wire contracts shared by edge, API, worker and UI."""
from __future__ import annotations

import time
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

Modality = Literal["thermal", "optical", "structural"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelemetryPacket(_Strict):
    node_id: str = Field(min_length=1, max_length=32)
    ts: float = Field(default_factory=time.time)
    temperature_c: float = Field(ge=-80, le=1500)
    vibration_mm_s: float = Field(ge=0, le=500)
    stress_pct: float = Field(ge=0, le=150)


class Detection(_Strict):
    label: str
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[float, float, float, float]  # x, y, w, h normalised to [0,1]


class AnomalyEvent(_Strict):
    id: str = Field(default_factory=lambda: uuid4().hex)
    node_id: str
    ts: float = Field(default_factory=time.time)
    modality: Modality
    label: str
    severity: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    detections: list[Detection] = Field(default_factory=list)
    telemetry: TelemetryPacket | None = None


class SwarmEvent(_Strict):
    thread_id: str
    node_id: str
    agent: str
    kind: Literal["thought", "result", "escalation", "status"]
    message: str
    ts: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)


class RemediationPlan(_Strict):
    action: str
    params: dict[str, float | str | bool]
    rationale: str
    citations: list[str]
    physical: bool


class ApprovalRequest(_Strict):
    thread_id: str
    node_id: str
    plan: RemediationPlan
    risk: float
    nonce: str
    created_at: float = Field(default_factory=time.time)
    expires_at: float


class ApprovalDecision(_Strict):
    thread_id: str
    approve: bool
    approver: str
    nonce: str
    token: str | None = None       # token mode (stripped by API after authentication)
    signature: str | None = None   # ed25519 mode / server attestation


class StreamEnvelope(_Strict):
    type: str
    data: dict[str, Any]
