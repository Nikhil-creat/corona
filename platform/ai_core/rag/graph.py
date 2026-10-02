"""Temporal knowledge graph: component aging, failure history and time-bounded dependencies."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any


class TemporalGraph(ABC):
    @abstractmethod
    async def upsert_component(self, cid: str, name: str, criticality: float, installed_at: float) -> None: ...
    @abstractmethod
    async def add_dependency(self, dependent: str, dependency: str, valid_from: float) -> None: ...
    @abstractmethod
    async def record_event(self, cid: str, kind: str, ts: float, details: dict[str, Any]) -> None: ...
    @abstractmethod
    async def context(self, cid: str, as_of: float | None = None) -> dict[str, Any]: ...


class MemoryGraph(TemporalGraph):
    def __init__(self) -> None:
        self.components: dict[str, dict[str, Any]] = {}
        self.deps: list[tuple[str, str, float, float | None]] = []
        self.events: dict[str, list[dict[str, Any]]] = {}

    async def upsert_component(self, cid, name, criticality, installed_at):
        self.components.setdefault(cid, {}).update(name=name, criticality=criticality, installed_at=installed_at)

    async def add_dependency(self, dependent, dependency, valid_from):
        if not any(d[0] == dependent and d[1] == dependency for d in self.deps):
            self.deps.append((dependent, dependency, valid_from, None))

    async def record_event(self, cid, kind, ts, details):
        self.events.setdefault(cid, []).append({"kind": kind, "ts": ts, "details": details})

    async def context(self, cid, as_of=None):
        t = as_of or time.time()
        comp = self.components.get(cid, {})
        # transitive dependents (who breaks if cid breaks), up to 3 hops, only edges valid at t
        frontier, seen = {cid}, set()
        for _ in range(3):
            frontier = {d for d, dep, vf, vt in self.deps if dep in frontier and vf <= t and (vt is None or vt > t)} - seen
            seen |= frontier
        evs = [e for e in self.events.get(cid, []) if e["ts"] <= t]
        return {
            "criticality": comp.get("criticality", 0.5),
            "age_days": (t - comp.get("installed_at", t)) / 86400,
            "dependents": sorted(seen),
            "failures_90d": sum(1 for e in evs if e["ts"] > t - 90 * 86400 and e["kind"].startswith("failure")),
            "recent_events": sorted(evs, key=lambda e: e["ts"], reverse=True)[:5],
        }


class Neo4jGraph(TemporalGraph):
    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import AsyncGraphDatabase

        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        async with self._driver.session() as s:
            res = await s.run(query, **params)
            return [r.data() async for r in res]

    async def upsert_component(self, cid, name, criticality, installed_at):
        await self._run(
            "MERGE (c:Component {id:$id}) SET c.name=$name, c.criticality=$crit, "
            "c.installed_at=coalesce(c.installed_at,$inst)", id=cid, name=name, crit=criticality, inst=installed_at)

    async def add_dependency(self, dependent, dependency, valid_from):
        await self._run(
            "MATCH (a:Component {id:$a}),(b:Component {id:$b}) MERGE (a)-[r:DEPENDS_ON]->(b) "
            "SET r.valid_from=coalesce(r.valid_from,$vf)", a=dependent, b=dependency, vf=valid_from)

    async def record_event(self, cid, kind, ts, details):
        await self._run(
            "MATCH (c:Component {id:$id}) CREATE (c)-[:HAD_EVENT]->(:Event {kind:$kind, ts:$ts, details:$d})",
            id=cid, kind=kind, ts=ts, d=json.dumps(details))

    async def context(self, cid, as_of=None):
        t = as_of or time.time()
        comp = (await self._run(
            "MATCH (c:Component {id:$id}) RETURN c.criticality AS crit, c.installed_at AS inst", id=cid) or [{}])[0]
        deps = await self._run(
            "MATCH p=(d:Component)-[:DEPENDS_ON*1..3]->(c:Component {id:$id}) "
            "WHERE ALL(r IN relationships(p) WHERE r.valid_from <= $t AND (r.valid_to IS NULL OR r.valid_to > $t)) "
            "RETURN DISTINCT d.id AS id", id=cid, t=t)
        evs = await self._run(
            "MATCH (:Component {id:$id})-[:HAD_EVENT]->(e:Event) WHERE e.ts <= $t "
            "RETURN e.kind AS kind, e.ts AS ts, e.details AS details ORDER BY e.ts DESC LIMIT 50", id=cid, t=t)
        return {
            "criticality": comp.get("crit", 0.5),
            "age_days": (t - (comp.get("inst") or t)) / 86400,
            "dependents": sorted(d["id"] for d in deps),
            "failures_90d": sum(1 for e in evs if e["ts"] > t - 90 * 86400 and e["kind"].startswith("failure")),
            "recent_events": [{"kind": e["kind"], "ts": e["ts"], "details": json.loads(e["details"] or "{}")} for e in evs[:5]],
        }
