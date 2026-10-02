"""Client-streaming gRPC ingest for edge gateways (generated stubs are created at image build time)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import grpc

from ai_core.common.container import Container
from ai_core.common.ingest import ingest_telemetry
from ai_core.common.schemas import TelemetryPacket

sys.path.insert(0, str(Path(__file__).parent / "generated"))
import telemetry_pb2 as pb  # noqa: E402
import telemetry_pb2_grpc as pb_grpc  # noqa: E402

log = logging.getLogger(__name__)


class TelemetryService(pb_grpc.TelemetryIngestServicer):
    def __init__(self, c: Container) -> None:
        self.c = c

    async def StreamTelemetry(self, request_iterator, context):  # noqa: N802
        accepted = 0
        async for m in request_iterator:
            try:
                await ingest_telemetry(self.c, TelemetryPacket(node_id=m.node_id, ts=m.ts, temperature_c=m.temperature_c,
                                                               vibration_mm_s=m.vibration_mm_s, stress_pct=m.stress_pct))
                accepted += 1
            except Exception as exc:
                log.warning("rejected packet: %s", exc)
        return pb.Ack(accepted=accepted)


async def serve(c: Container, port: int = 50051) -> grpc.aio.Server:
    server = grpc.aio.server()
    pb_grpc.add_TelemetryIngestServicer_to_server(TelemetryService(c), server)
    server.add_insecure_port(f"[::]:{port}")  # terminate TLS/mTLS at the mesh / ingress in production
    await server.start()
    return server
