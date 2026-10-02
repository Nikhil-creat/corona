"""Federated learning: FedAvg with update clipping + Gaussian noise (DP-style), min-participation rounds.
Works on dict[str, np.ndarray] so it is framework-agnostic (convert torch state_dict via .numpy())."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field

import numpy as np

Weights = dict[str, np.ndarray]


def pack(w: Weights) -> str:
    buf = io.BytesIO()
    np.savez_compressed(buf, **w)
    return base64.b64encode(buf.getvalue()).decode()


def unpack(s: str) -> Weights:
    with np.load(io.BytesIO(base64.b64decode(s))) as z:
        return {k: z[k] for k in z.files}


def fedavg(updates: list[tuple[Weights, int]]) -> Weights:
    total = sum(n for _, n in updates)
    if total <= 0:
        raise ValueError("no samples")
    keys = updates[0][0].keys()
    return {k: sum(w[k].astype(np.float64) * (n / total) for w, n in updates).astype(updates[0][0][k].dtype) for k in keys}


def clip_delta(delta: Weights, max_norm: float) -> Weights:
    norm = float(np.sqrt(sum(float((d.astype(np.float64) ** 2).sum()) for d in delta.values())))
    scale = min(1.0, max_norm / (norm + 1e-12))
    return {k: (d * scale).astype(d.dtype) for k, d in delta.items()}


@dataclass
class FederatedCoordinator:
    global_weights: Weights
    min_clients: int = 3
    clip_norm: float = 5.0
    noise_std: float = 0.0
    version: int = 0
    _pending: dict[str, tuple[Weights, int]] = field(default_factory=dict)
    _rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(7))

    def submit(self, client_id: str, delta: Weights, num_samples: int) -> dict | None:
        """Accept a client weight *delta*; returns round summary when aggregation fires."""
        self._pending[client_id] = (clip_delta(delta, self.clip_norm), max(int(num_samples), 1))
        if len(self._pending) < self.min_clients:
            return None
        avg = fedavg(list(self._pending.values()))
        for k, d in avg.items():
            noise = self._rng.normal(0, self.noise_std, d.shape).astype(d.dtype) if self.noise_std else 0
            self.global_weights[k] = self.global_weights[k] + d + noise
        n = len(self._pending)
        self._pending.clear()
        self.version += 1
        return {"version": self.version, "clients": n}
