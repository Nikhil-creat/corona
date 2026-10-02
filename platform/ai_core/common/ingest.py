"""Single entry points for writing telemetry/anomalies so edge, HTTP and gRPC paths behave identically."""
from __future__ import annotations

from .container import Container
from .schemas import AnomalyEvent, TelemetryPacket
from .topics import Topics


async def ingest_telemetry(c: Container, packet: TelemetryPacket) -> None:
    await c.state.set(f"node:{packet.node_id}:latest", packet.model_dump(mode="json"), ttl=300)
    await c.state.lpush_trim(f"node:{packet.node_id}:history", packet.model_dump(mode="json"), 120)
    await c.bus.publish(Topics.TELEMETRY, packet, key=packet.node_id)


async def ingest_anomaly(c: Container, event: AnomalyEvent) -> None:
    doc = event.model_dump(mode="json")
    await c.state.lpush_trim(f"anomalies:{event.node_id}", doc, 50)
    await c.state.lpush_trim("anomalies:recent", doc, 100)
    await c.bus.publish(Topics.ANOMALIES, event, key=event.node_id)
