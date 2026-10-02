"""Hybrid retrieval with re-ranking and an abstention gate (zero-hallucination contract):
agents may only act on evidence that survives `min_score`; otherwise retrieve() returns []."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from .embeddings import Embedder
from .stores import Hit, VectorStore

_TOK = re.compile(r"[a-z0-9]+")


@dataclass
class Evidence:
    chunk_id: str
    doc_id: str
    text: str
    score: float
    source: str


class LexicalReranker:
    def rerank(self, query: str, hits: list[Hit]) -> list[tuple[Hit, float]]:
        q = set(_TOK.findall(query.lower()))
        out = []
        for h in hits:
            d = set(_TOK.findall(h.text.lower()))
            overlap = len(q & d) / max(len(q), 1)
            out.append((h, 0.5 * max(h.score, 0.0) + 0.5 * overlap))
        return sorted(out, key=lambda t: t[1], reverse=True)


class CrossEncoderReranker:
    def __init__(self, model: str) -> None:
        from sentence_transformers import CrossEncoder

        self._m = CrossEncoder(model)

    def rerank(self, query: str, hits: list[Hit]) -> list[tuple[Hit, float]]:
        if not hits:
            return []
        raw = self._m.predict([(query, h.text) for h in hits])
        scores = [1 / (1 + pow(2.718281828, -float(s))) for s in raw]  # squash logits → (0,1)
        return sorted(zip(hits, scores), key=lambda t: t[1], reverse=True)


class HybridRetriever:
    def __init__(self, store: VectorStore, embedder: Embedder, reranker, min_score: float) -> None:
        self.store, self.embedder, self.reranker, self.min_score = store, embedder, reranker, min_score

    async def retrieve(self, query: str, k: int = 12, top_n: int = 4) -> list[Evidence]:
        qv = self.embedder.embed([query])[0]
        hits = await self.store.search(qv, k)
        now = time.time()
        # temporal validity: ignore superseded / not-yet-effective documents
        hits = [h for h in hits if h.meta.get("effective_from", 0) <= now < h.meta.get("effective_to", float("inf"))]
        ranked = self.reranker.rerank(query, hits)
        return [
            Evidence(h.chunk_id, h.doc_id, h.text, round(s, 4), h.meta.get("source", h.doc_id))
            for h, s in ranked[:top_n]
            if s >= self.min_score
        ]
