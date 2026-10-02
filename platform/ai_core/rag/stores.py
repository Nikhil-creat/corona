from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from .chunker import Chunk


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    meta: dict[str, Any]


class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...
    @abstractmethod
    async def search(self, vector: np.ndarray, k: int) -> list[Hit]: ...
    @abstractmethod
    async def count(self) -> int: ...


class MemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._rows: dict[str, tuple[Chunk, np.ndarray]] = {}

    async def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        for c, v in zip(chunks, vectors):
            self._rows[c.id] = (c, v)

    async def search(self, vector: np.ndarray, k: int) -> list[Hit]:
        scored = [(float(np.dot(vector, v)), c) for c, v in self._rows.values()]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [Hit(c.id, c.doc_id, c.text, s, c.meta) for s, c in scored[:k]]

    async def count(self) -> int:
        return len(self._rows)


def _vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"


class PgVectorStore(VectorStore):
    """pgvector (HNSW, cosine). One short-lived connection per call; put a pool (psycopg_pool) in front for load."""

    def __init__(self, dsn: str, dim: int) -> None:
        self._dsn, self._dim, self._ready = dsn, dim, False

    async def _conn(self):
        import psycopg

        conn = await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)
        if not self._ready:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS doc_chunks (id text PRIMARY KEY, doc_id text NOT NULL, "
                f"text text NOT NULL, meta jsonb NOT NULL DEFAULT '{{}}', embedding vector({int(self._dim)}))"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS doc_chunks_hnsw ON doc_chunks USING hnsw (embedding vector_cosine_ops)"
            )
            self._ready = True
        return conn

    async def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        conn = await self._conn()
        try:
            async with conn.cursor() as cur:
                for c, v in zip(chunks, vectors):
                    await cur.execute(
                        "INSERT INTO doc_chunks (id, doc_id, text, meta, embedding) VALUES (%s,%s,%s,%s::jsonb,%s::vector) "
                        "ON CONFLICT (id) DO UPDATE SET text=EXCLUDED.text, meta=EXCLUDED.meta, embedding=EXCLUDED.embedding",
                        (c.id, c.doc_id, c.text, json.dumps(c.meta), _vec(v)),
                    )
        finally:
            await conn.close()

    async def search(self, vector: np.ndarray, k: int) -> list[Hit]:
        conn = await self._conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, doc_id, text, meta, 1 - (embedding <=> %s::vector) AS score "
                    "FROM doc_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
                    (_vec(vector), _vec(vector), k),
                )
                rows = await cur.fetchall()
        finally:
            await conn.close()
        return [Hit(r[0], r[1], r[2], float(r[4]), r[3] or {}) for r in rows]

    async def count(self) -> int:
        conn = await self._conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT count(*) FROM doc_chunks")
                return int((await cur.fetchone())[0])
        finally:
            await conn.close()
