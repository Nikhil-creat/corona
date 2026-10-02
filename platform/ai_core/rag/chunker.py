"""Semantic chunking: split on sentence boundaries, cut where topical similarity drops or size is hit."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .embeddings import Embedder

_SPLIT = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass
class Chunk:
    id: str
    doc_id: str
    text: str
    meta: dict[str, Any] = field(default_factory=dict)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s and s.strip()]


def semantic_chunks(text: str, embedder: Embedder, max_chars: int = 900, min_chars: int = 220,
                    threshold: float = 0.12) -> list[str]:
    sents = split_sentences(text)
    if not sents:
        return []
    embs = embedder.embed(sents)
    chunks: list[str] = []
    cur: list[int] = [0]
    for i in range(1, len(sents)):
        cur_len = sum(len(sents[j]) for j in cur) + len(cur)
        centroid = embs[cur[-3:]].mean(axis=0)
        sim = float(np.dot(centroid, embs[i]) / (np.linalg.norm(centroid) * np.linalg.norm(embs[i]) + 1e-9))
        if cur_len + len(sents[i]) > max_chars or (cur_len >= min_chars and sim < threshold):
            chunks.append(" ".join(sents[j] for j in cur))
            cur = []
        cur.append(i)
    chunks.append(" ".join(sents[j] for j in cur))
    return chunks
