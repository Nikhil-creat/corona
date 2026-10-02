"""Dependency container: constructs infrastructure clients once and injects them everywhere."""
from __future__ import annotations

import time
from dataclasses import dataclass

from security.approvals import ApprovalVerifier

from ai_core.rag.embeddings import Embedder, make_embedder
from ai_core.rag.graph import MemoryGraph, Neo4jGraph, TemporalGraph
from ai_core.rag.ingest import IngestionPipeline
from ai_core.rag.retriever import CrossEncoderReranker, HybridRetriever, LexicalReranker
from ai_core.rag.stores import MemoryVectorStore, PgVectorStore, VectorStore

from .bus import EventBus, get_bus
from .config import Settings, get_settings
from .state import StateStore, get_state
from .topology import EDGES, NODES


@dataclass
class Container:
    settings: Settings
    bus: EventBus
    state: StateStore
    embedder: Embedder
    store: VectorStore
    graph: TemporalGraph
    retriever: HybridRetriever
    pipeline: IngestionPipeline
    verifier: ApprovalVerifier


async def seed_topology(graph: TemporalGraph) -> None:
    installed = time.time() - 4 * 365 * 86400
    for n in NODES:
        await graph.upsert_component(n["id"], n["name"], n["criticality"], installed)
    for dependent, dependency in EDGES:
        await graph.add_dependency(dependent, dependency, installed)


async def build_container(settings: Settings | None = None) -> Container:
    s = settings or get_settings()
    embedder = make_embedder(s.embedding_backend, s.embedding_model, s.embedding_dim)
    store: VectorStore = MemoryVectorStore() if s.use_in_memory else PgVectorStore(s.postgres_dsn, embedder.dim)
    graph: TemporalGraph = MemoryGraph() if s.use_in_memory else Neo4jGraph(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    reranker = CrossEncoderReranker(s.rerank_model) if s.rerank_backend == "cross-encoder" else LexicalReranker()
    return Container(
        settings=s,
        bus=get_bus(),
        state=get_state(),
        embedder=embedder,
        store=store,
        graph=graph,
        retriever=HybridRetriever(store, embedder, reranker, s.min_evidence_score),
        pipeline=IngestionPipeline(store, embedder),
        verifier=ApprovalVerifier(s.approval_mode, s.tokens, s.pubkeys, s.approval_hmac_secret),
    )
