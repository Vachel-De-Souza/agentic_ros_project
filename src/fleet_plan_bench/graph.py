"""Site graph helpers: edge lookup, route length, no-go-aware shortest paths."""

from __future__ import annotations

import heapq
from collections.abc import Sequence
from itertools import pairwise

from fleet_plan_bench.schemas import Edge, Site


class SiteGraph:
    def __init__(self, site: Site) -> None:
        self.site = site
        self.zones = {z.id: z for z in site.zones}
        self.stations = set(site.charging_stations)
        self._edges: dict[frozenset[str], Edge] = {}
        self._adj: dict[str, list[str]] = {z: [] for z in self.zones}
        for e in site.edges:
            self._edges[frozenset((e.a, e.b))] = e
            self._adj[e.a].append(e.b)
            self._adj[e.b].append(e.a)
        for nbrs in self._adj.values():
            nbrs.sort()

    def edge(self, a: str, b: str) -> Edge | None:
        return self._edges.get(frozenset((a, b)))

    def neighbors(self, zone: str) -> list[str]:
        return self._adj.get(zone, [])

    def is_passable(self, a: str, b: str) -> bool:
        e = self.edge(a, b)
        return e is not None and not e.no_go and not self.zones[b].no_go

    def route_length(self, route: Sequence[str]) -> float:
        """Sum of edge distances; repeated zones cost 0; missing edges count as 0."""
        total = 0.0
        for a, b in pairwise(route):
            if a != b and (e := self.edge(a, b)) is not None:
                total += e.distance
        return total

    def shortest_path(self, src: str, dst: str) -> tuple[list[str], float] | None:
        """Deterministic Dijkstra avoiding no-go zones and edges. None if unreachable."""
        if src not in self.zones or dst not in self.zones:
            return None
        if src == dst:
            return [src], 0.0
        heap: list[tuple[float, list[str]]] = [(0.0, [src])]
        best: dict[str, float] = {src: 0.0}
        while heap:
            d, path = heapq.heappop(heap)
            node = path[-1]
            if node == dst:
                return path, d
            if d > best.get(node, float("inf")):
                continue
            for nxt in self.neighbors(node):
                if not self.is_passable(node, nxt):
                    continue
                e = self.edge(node, nxt)
                assert e is not None
                nd = d + e.distance
                if nd < best.get(nxt, float("inf")) - 1e-12:
                    best[nxt] = nd
                    heapq.heappush(heap, (nd, [*path, nxt]))
        return None

    def all_pairs(self) -> dict[tuple[str, str], tuple[list[str], float]]:
        out: dict[tuple[str, str], tuple[list[str], float]] = {}
        for a in self.zones:
            for b in self.zones:
                r = self.shortest_path(a, b)
                if r is not None:
                    out[(a, b)] = r
        return out
