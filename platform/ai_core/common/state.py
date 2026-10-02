"""Key/value + list state store (Redis / Redis Cluster in prod, dict in dev/tests)."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from .config import get_settings


class StateStore(ABC):
    @abstractmethod
    async def get(self, key: str) -> Any | None: ...
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    @abstractmethod
    async def delete(self, key: str) -> None: ...
    @abstractmethod
    async def set_if_absent(self, key: str, value: Any, ttl: int | None = None) -> bool: ...
    @abstractmethod
    async def lpush_trim(self, key: str, value: Any, maxlen: int) -> None: ...
    @abstractmethod
    async def lrange(self, key: str, start: int, stop: int) -> list[Any]: ...
    @abstractmethod
    async def keys(self, prefix: str) -> list[str]: ...


class MemoryState(StateStore):
    def __init__(self) -> None:
        self._kv: dict[str, tuple[Any, float | None]] = {}
        self._lists: dict[str, list[Any]] = {}

    def _live(self, key: str) -> Any | None:
        item = self._kv.get(key)
        if item is None:
            return None
        value, exp = item
        if exp is not None and exp < time.time():
            self._kv.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> Any | None:
        return self._live(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._kv[key] = (value, time.time() + ttl if ttl else None)

    async def delete(self, key: str) -> None:
        self._kv.pop(key, None)
        self._lists.pop(key, None)

    async def set_if_absent(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if self._live(key) is not None:
            return False
        await self.set(key, value, ttl)
        return True

    async def lpush_trim(self, key: str, value: Any, maxlen: int) -> None:
        lst = self._lists.setdefault(key, [])
        lst.insert(0, value)
        del lst[maxlen:]

    async def lrange(self, key: str, start: int, stop: int) -> list[Any]:
        lst = self._lists.get(key, [])
        return lst[start : (stop + 1) if stop >= 0 else None]

    async def keys(self, prefix: str) -> list[str]:
        return [k for k in list(self._kv) if k.startswith(prefix) and self._live(k) is not None]


class RedisState(StateStore):
    def __init__(self, url: str, cluster: bool = False) -> None:
        if cluster:
            from redis.asyncio.cluster import RedisCluster

            self._r: Any = RedisCluster.from_url(url, decode_responses=True)
        else:
            from redis.asyncio import Redis

            self._r = Redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Any | None:
        raw = await self._r.get(key)
        return json.loads(raw) if raw is not None else None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self._r.set(key, json.dumps(value), ex=ttl)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def set_if_absent(self, key: str, value: Any, ttl: int | None = None) -> bool:
        return bool(await self._r.set(key, json.dumps(value), ex=ttl, nx=True))

    async def lpush_trim(self, key: str, value: Any, maxlen: int) -> None:
        pipe = self._r.pipeline()
        pipe.lpush(key, json.dumps(value))
        pipe.ltrim(key, 0, maxlen - 1)
        await pipe.execute()

    async def lrange(self, key: str, start: int, stop: int) -> list[Any]:
        return [json.loads(x) for x in await self._r.lrange(key, start, stop)]

    async def keys(self, prefix: str) -> list[str]:
        return [k async for k in self._r.scan_iter(match=f"{prefix}*", count=200)]


@lru_cache
def get_state() -> StateStore:
    s = get_settings()
    return MemoryState() if s.use_in_memory else RedisState(s.redis_url, s.redis_cluster)
