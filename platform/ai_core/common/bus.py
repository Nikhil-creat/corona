"""Event bus abstraction: Kafka/Redpanda in production, in-process queues for dev/tests."""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, AsyncIterator, Sequence

from pydantic import BaseModel

from .config import Settings, get_settings

log = logging.getLogger(__name__)
Message = tuple[str, dict[str, Any]]


def to_dict(payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload


class Subscription(ABC):
    @abstractmethod
    def __aiter__(self) -> AsyncIterator[Message]: ...

    @abstractmethod
    async def close(self) -> None: ...


class EventBus(ABC):
    async def start(self) -> None:  # pragma: no cover - trivial
        return None

    async def stop(self) -> None:  # pragma: no cover - trivial
        return None

    @abstractmethod
    async def publish(self, topic: str, payload: BaseModel | dict[str, Any], key: str | None = None) -> None: ...

    @abstractmethod
    async def subscribe(self, topics: Sequence[str], group: str, from_start: bool = False) -> Subscription: ...


# ───────────────────────── in-memory ─────────────────────────
class _MemSub(Subscription):
    def __init__(self, queue: asyncio.Queue[Message | None]) -> None:
        self._q = queue

    async def __aiter__(self) -> AsyncIterator[Message]:  # type: ignore[override]
        while True:
            item = await self._q.get()
            if item is None:
                return
            yield item

    async def close(self) -> None:
        self._q.put_nowait(None)


class MemoryBus(EventBus):
    """Consumer groups share one queue (competing consumers); distinct groups each get every message."""

    def __init__(self) -> None:
        self._groups: dict[str, tuple[set[str], asyncio.Queue[Message | None]]] = {}

    async def publish(self, topic: str, payload: BaseModel | dict[str, Any], key: str | None = None) -> None:
        data = to_dict(payload)
        for topics, queue in self._groups.values():
            if topic in topics:
                queue.put_nowait((topic, data))

    async def subscribe(self, topics: Sequence[str], group: str, from_start: bool = False) -> Subscription:
        topic_set, queue = self._groups.setdefault(group, (set(), asyncio.Queue()))
        topic_set.update(topics)
        return _MemSub(queue)


# ───────────────────────── Kafka / Redpanda ─────────────────────────
class _KafkaSub(Subscription):
    def __init__(self, consumer: Any) -> None:
        self._c = consumer

    async def __aiter__(self) -> AsyncIterator[Message]:  # type: ignore[override]
        async for msg in self._c:
            try:
                yield msg.topic, json.loads(msg.value)
            except (ValueError, TypeError):
                log.warning("dropping undecodable message on %s", msg.topic)

    async def close(self) -> None:
        await self._c.stop()


class KafkaBus(EventBus):
    def __init__(self, bootstrap: str) -> None:
        self._bootstrap = bootstrap
        self._producer: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_producer(self) -> Any:
        async with self._lock:
            if self._producer is None:
                from aiokafka import AIOKafkaProducer

                producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap, linger_ms=5)
                await producer.start()
                self._producer = producer
        return self._producer

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, payload: BaseModel | dict[str, Any], key: str | None = None) -> None:
        producer = await self._ensure_producer()
        await producer.send(topic, json.dumps(to_dict(payload)).encode(), key=key.encode() if key else None)

    async def subscribe(self, topics: Sequence[str], group: str, from_start: bool = False) -> Subscription:
        from aiokafka import AIOKafkaConsumer

        consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=self._bootstrap,
            group_id=group,
            auto_offset_reset="earliest" if from_start else "latest",
            enable_auto_commit=True,
        )
        await consumer.start()
        return _KafkaSub(consumer)


@lru_cache
def get_bus() -> EventBus:
    settings: Settings = get_settings()
    return MemoryBus() if settings.use_in_memory else KafkaBus(settings.kafka_bootstrap)
