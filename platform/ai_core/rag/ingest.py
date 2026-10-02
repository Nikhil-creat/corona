"""Ingestion worker: PDFs, markdown/text, CAD-metadata JSON and compliance logs → semantic chunks → vector store."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from .chunker import Chunk, semantic_chunks
from .embeddings import Embedder
from .stores import VectorStore

SEED_DIR = Path(__file__).parent / "seed_docs"


def _flatten_json(obj: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lines += _flatten_json(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            lines += _flatten_json(v, f"{prefix}{i}.")
    else:
        lines.append(f"{prefix.rstrip('.')}: {obj}.")
    return lines


class IngestionPipeline:
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self.store, self.embedder = store, embedder

    async def ingest_text(self, doc_id: str, text: str, meta: dict[str, Any] | None = None) -> int:
        meta = {"source": doc_id, "effective_from": 0, **(meta or {})}
        pieces = semantic_chunks(text, self.embedder)
        chunks = [
            Chunk(hashlib.sha1(f"{doc_id}:{i}:{p}".encode()).hexdigest()[:16], doc_id, p, {**meta, "ord": i})
            for i, p in enumerate(pieces)
        ]
        if chunks:
            await self.store.upsert(chunks, self.embedder.embed([c.text for c in chunks]))
        return len(chunks)

    async def ingest_file(self, path: Path) -> int:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            from pypdf import PdfReader

            text = "\n\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        elif suffix == ".json":
            text = "\n".join(_flatten_json(json.loads(path.read_text())))
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        return await self.ingest_text(path.stem, text, {"source": path.name, "ingested_at": time.time()})

    async def ingest_dir(self, root: Path) -> int:
        total = 0
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".pdf", ".md", ".txt", ".json"}:
                total += await self.ingest_file(p)
        return total

    async def seed_if_empty(self) -> int:
        return 0 if await self.store.count() else await self.ingest_dir(SEED_DIR)


async def _main(path: str) -> None:  # python -m ai_core.rag.ingest ./docs
    from ai_core.common.container import build_container

    c = await build_container()
    print(f"ingested {await c.pipeline.ingest_dir(Path(path))} chunks")


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1] if len(sys.argv) > 1 else str(SEED_DIR)))
