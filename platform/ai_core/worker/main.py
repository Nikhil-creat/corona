"""Swarm worker: anomalies → isolated LangGraph threads; approval decisions → resume; FL updates → aggregate."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from ai_core.agents.graph import SwarmRunner
from ai_core.common.container import Container, build_container, seed_topology
from ai_core.common.schemas import AnomalyEvent, ApprovalDecision
from ai_core.common.telemetry import setup_observability
from ai_core.common.topics import Topics
from ai_core.vision.federated import FederatedCoordinator, unpack

log = logging.getLogger("worker")


async def _anomaly_loop(c: Container, runner: SwarmRunner, runs: Any) -> None:
    sem = asyncio.Semaphore(16)
    sub = await c.bus.subscribe([Topics.ANOMALIES], group="swarm", from_start=False)

    async def handle(raw: dict[str, Any]) -> None:
        async with sem:
            event = AnomalyEvent(**raw)
            # dedupe storms: one live thread per node+label
            if not await c.state.set_if_absent(f"swarm:active:{event.node_id}:{event.label}", event.id, ttl=45):
                return
            final = await runner.run(event)
            runs.labels(final.get("status", "unknown")).inc()
            log.info("thread %s → %s", event.id[:8], final.get("status"))

    async for _, raw in sub:
        asyncio.create_task(handle(raw))


async def _decision_loop(c: Container, runner: SwarmRunner) -> None:
    sub = await c.bus.subscribe([Topics.APPROVAL_DECISIONS], group="swarm-decisions", from_start=False)
    async for _, raw in sub:
        try:
            final = await runner.resume(ApprovalDecision(**raw))
            log.info("decision for %s → %s", raw.get("thread_id"), final.get("status") if final else "ignored")
        except Exception:
            log.exception("failed to process approval decision")


async def _federated_loop(c: Container) -> None:
    coord = FederatedCoordinator({"head.weight": np.zeros((4, 8), dtype="float32")}, min_clients=1)
    sub = await c.bus.subscribe([Topics.FL_UPDATES], group="fl", from_start=False)
    async for _, raw in sub:
        try:
            summary = coord.submit(raw["client_id"], unpack(raw["delta"]), raw["num_samples"])
            if summary:
                await c.bus.publish(Topics.FL_GLOBAL, summary)
        except Exception:
            log.exception("bad federated update")


_RUNS: Any = None


def _runs_counter() -> Any:
    global _RUNS
    if _RUNS is None:
        from prometheus_client import Counter

        _RUNS = Counter("aether_swarm_runs_total", "completed swarm threads", ["status"])
    return _RUNS


async def start_worker(c: Container) -> list[asyncio.Task]:
    await seed_topology(c.graph)
    seeded = await c.pipeline.seed_if_empty()
    if seeded:
        log.info("seeded knowledge base with %d chunks", seeded)
    runs = _runs_counter()
    runner = SwarmRunner(c)
    return [asyncio.create_task(_anomaly_loop(c, runner, runs)),
            asyncio.create_task(_decision_loop(c, runner)),
            asyncio.create_task(_federated_loop(c))]


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    c = await build_container()
    setup_observability("swarm-worker", c.settings, metrics_port=9101)
    tasks = await start_worker(c)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
