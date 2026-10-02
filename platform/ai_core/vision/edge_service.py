"""Edge node process: sensors/cameras → inference → telemetry + anomalies on the bus, plus federated updates."""
from __future__ import annotations

import asyncio
import logging
import random
import time

import numpy as np

from ai_core.common.container import build_container
from ai_core.common.ingest import ingest_anomaly, ingest_telemetry
from ai_core.common.telemetry import setup_observability
from ai_core.common.topics import Topics
from ai_core.common.topology import NODE_IDS

from .federated import pack
from .simulator import NodeSimulator, SimulatedDetector

log = logging.getLogger("edge")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    c = await build_container()
    setup_observability("edge-vision", c.settings, metrics_port=9102)
    from prometheus_client import Counter

    frames = Counter("aether_edge_frames_total", "frames/packets processed", ["node"])
    anomalies = Counter("aether_edge_anomalies_total", "anomalies emitted", ["label"])

    rng = random.Random(42)
    sims = {nid: NodeSimulator(nid, random.Random(rng.random())) for nid in NODE_IDS}
    sim_detector = SimulatedDetector(rng)
    torch_detector = None
    if c.settings.vision_backend == "torch":
        from .torch_detector import TorchDetector

        torch_detector = TorchDetector(c.settings.vision_weights)
    streams = dict(p.split("=", 1) for p in c.settings.rtsp_urls.split(",") if "=" in p)
    sources = {}
    if torch_detector and streams:
        from .torch_detector import FrameSource

        sources = {nid: FrameSource(url) for nid, url in streams.items()}

    fl_round = 0
    period = 1.0 / max(c.settings.edge_tick_hz, 0.1)
    last_emit: dict[str, float] = {}
    log.info("edge online: %d nodes, backend=%s", len(sims), c.settings.vision_backend)
    while True:
        started = time.time()
        for nid, sim in sims.items():
            pkt, label, sev = sim.step()
            await ingest_telemetry(c, pkt)
            frames.labels(nid).inc()
            event = None
            if torch_detector and nid in sources:
                frame = await asyncio.to_thread(sources[nid].read)
                if frame is not None:
                    event = await asyncio.to_thread(torch_detector.detect, frame, None, pkt)
            else:
                event = sim_detector.detect(pkt, label, sev)
            if event and time.time() - last_emit.get(nid, 0) > 20:  # per-node alert debounce
                last_emit[nid] = time.time()
                await ingest_anomaly(c, event)
                anomalies.labels(event.label).inc()
                log.info("anomaly %s on %s sev=%.2f conf=%.2f", event.label, nid, event.severity, event.confidence)
        fl_round += 1
        if fl_round % 120 == 0:  # demo federated update: tiny synthetic delta from this edge cluster
            delta = {"head.weight": np.random.default_rng(fl_round).normal(0, 0.01, (4, 8)).astype("float32")}
            await c.bus.publish(Topics.FL_UPDATES, {"client_id": "edge-cluster-1", "num_samples": 512, "delta": pack(delta)})
        await asyncio.sleep(max(0.0, period - (time.time() - started)))


if __name__ == "__main__":
    asyncio.run(main())
