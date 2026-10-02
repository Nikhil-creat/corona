"""Centralised, validated runtime configuration (12-factor, env driven)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    env: str = "dev"
    use_in_memory: bool = False
    embedded_worker: bool = False

    kafka_bootstrap: str = "redpanda:9092"
    redis_url: str = "redis://redis:6379/0"
    redis_cluster: bool = False
    postgres_dsn: str = "postgresql://aether:aether@postgres:5432/aether"
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change-me-neo4j"
    otel_endpoint: str = ""

    api_keys: str = "dev-api-key"
    cors_origins: str = "http://localhost:3000"
    approval_mode: str = "token"  # token | ed25519
    approver_tokens: str = "ops-lead:dev-approver-token"
    approver_pubkeys: str = ""
    approval_hmac_secret: str = "change-me-hmac-secret-32-bytes-min"
    approval_ttl_s: int = 900
    hitl_risk_threshold: float = 0.6
    pq_required: bool = False

    embedding_backend: str = "hashing"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    rerank_backend: str = "lexical"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    min_evidence_score: float = 0.15

    vision_backend: str = "simulated"
    vision_weights: str = "/models/hybrid_spatialnet.pt"
    rtsp_urls: str = ""
    edge_tick_hz: float = 2.0

    @staticmethod
    def _pairs(raw: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in filter(None, (p.strip() for p in raw.split(","))):
            name, _, value = item.partition(":")
            if name and value:
                out[name.strip()] = value.strip()
        return out

    @property
    def api_key_set(self) -> frozenset[str]:
        return frozenset(k.strip() for k in self.api_keys.split(",") if k.strip())

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tokens(self) -> dict[str, str]:
        return self._pairs(self.approver_tokens)

    @property
    def pubkeys(self) -> dict[str, str]:
        return self._pairs(self.approver_pubkeys)


@lru_cache
def get_settings() -> Settings:
    return Settings()
