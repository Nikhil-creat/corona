from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.responses import Response

from ai_core.common.container import build_container
from ai_core.common.config import get_settings
from ai_core.common.telemetry import setup_observability
from ai_core.common.topics import Topics
from ai_core.worker.main import start_worker

from .hub import ConnectionHub
from .routes.api import router

log = logging.getLogger("api")
WS_CLIENTS = Gauge("aether_ws_clients", "connected WebSocket clients")


async def _relay(app: FastAPI) -> None:
    c, hub = app.state.container, app.state.hub
    sub = await c.bus.subscribe(Topics.UI_STREAM, group=f"api-{os.getpid()}-{id(app)}")
    async for topic, data in sub:
        await hub.broadcast({"type": topic, "data": data})


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.container = c = await build_container(settings)
    app.state.hub = ConnectionHub()
    setup_observability("api", settings)
    tasks = [asyncio.create_task(_relay(app))]
    if settings.embedded_worker:
        tasks += await start_worker(c)
    grpc_server = None
    if os.getenv("GRPC_ENABLED", "false").lower() == "true":
        from .grpc_server import serve

        grpc_server = await serve(c)
    await asyncio.sleep(0)  # let subscriptions register before serving
    yield
    if grpc_server:
        await grpc_server.stop(2)
    for t in tasks:
        t.cancel()
    await c.bus.stop()


app = FastAPI(title="Corona API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(router)

if get_settings().otel_endpoint:
    with contextlib.suppress(Exception):
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    c = app.state.container
    return {"status": "ready", "kb_chunks": await c.store.count()}


@app.get("/metrics")
async def metrics() -> Response:
    WS_CLIENTS.set(len(app.state.hub))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.websocket("/ws/stream")
async def stream(ws: WebSocket, key: str = "") -> None:
    c, hub = app.state.container, app.state.hub
    if not any(hmac.compare_digest(key, k) for k in c.settings.api_key_set):
        await ws.close(code=4401)
        return
    await hub.add(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive / ignore client chatter
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(ws)
