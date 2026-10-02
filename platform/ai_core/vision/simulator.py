"""Physics-flavoured sensor + detector simulator (default vision backend; no GPU/weights needed)."""
from __future__ import annotations

import random
from dataclasses import dataclass

from ai_core.common.schemas import AnomalyEvent, Detection, TelemetryPacket

from .labels import MODALITY

FAULTS = ["thermal_overheat", "bearing_wear", "structural_crack", "electrical_fault"]


@dataclass
class _Fault:
    label: str
    ticks_left: int
    peak: float


class NodeSimulator:
    def __init__(self, node_id: str, rng: random.Random, fault_rate: float = 0.004) -> None:
        self.node_id, self.rng, self.fault_rate = node_id, rng, fault_rate
        self.temp, self.vib, self.stress = rng.uniform(52, 64), rng.uniform(1.5, 3), rng.uniform(25, 40)
        self.fault: _Fault | None = None
        self.cooldown = 0

    def step(self) -> tuple[TelemetryPacket, str | None, float]:
        r = self.rng
        self.temp += r.gauss(0, 0.6) + (58 - self.temp) * 0.05
        self.vib += r.gauss(0, 0.1) + (2.2 - self.vib) * 0.08
        self.stress += r.gauss(0, 0.5) + (32 - self.stress) * 0.05
        if self.fault is None and self.cooldown == 0 and r.random() < self.fault_rate:
            self.fault = _Fault(r.choice(FAULTS), r.randint(14, 24), r.uniform(0.55, 0.98))
        label, sev = None, 0.0
        if self.fault:
            f = self.fault
            sev = min(f.peak, f.peak * (1 - f.ticks_left / 28))
            if f.label in ("thermal_overheat", "electrical_fault"):
                self.temp += 3.2 * f.peak
            elif f.label == "bearing_wear":
                self.vib += 0.9 * f.peak
            else:
                self.stress += 3.8 * f.peak
                self.vib += 0.25 * f.peak
            f.ticks_left -= 1
            label = f.label
            if f.ticks_left <= 0:
                self.fault, self.cooldown = None, 60
        else:
            self.cooldown = max(0, self.cooldown - 1)
        pkt = TelemetryPacket(node_id=self.node_id, temperature_c=max(-50, min(self.temp, 400)),
                              vibration_mm_s=max(0, min(self.vib, 100)), stress_pct=max(0, min(self.stress, 140)))
        return pkt, label, sev


class SimulatedDetector:
    """Stands in for the ViT/CNN: emits boxes + confidence when the simulated fault becomes visible."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def detect(self, pkt: TelemetryPacket, label: str | None, severity: float) -> AnomalyEvent | None:
        if label is None or severity < 0.35:
            return None
        conf = min(0.99, 0.45 + severity * 0.5 + self.rng.uniform(-0.06, 0.06))
        x, y = self.rng.uniform(0.15, 0.6), self.rng.uniform(0.15, 0.55)
        det = Detection(label=label, confidence=round(conf, 3), bbox=(round(x, 3), round(y, 3), 0.28, 0.24))
        return AnomalyEvent(node_id=pkt.node_id, modality=MODALITY[label], label=label,  # type: ignore[arg-type]
                            severity=round(severity, 3), confidence=round(conf, 3), detections=[det], telemetry=pkt)
