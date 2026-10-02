from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    """Deterministic, dependency-free feature-hashing embedder (unigrams + bigrams).
    Great for offline dev/CI; use sentence-transformers in production."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _idx(self, tok: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        return h % self.dim, 1.0 if (h >> 63) & 1 else -1.0

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            toks = _TOKEN.findall(text.lower())
            for t in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]:
                j, sign = self._idx(t)
                out[i, j] += sign
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.clip(norms, 1e-9, None)


class SentenceTransformerEmbedder:
    def __init__(self, model: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._m = SentenceTransformer(model)
        self.dim = int(self._m.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._m.encode(texts, normalize_embeddings=True), dtype=np.float32)


def make_embedder(backend: str, model: str, dim: int) -> Embedder:
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model)
    return HashingEmbedder(dim)
