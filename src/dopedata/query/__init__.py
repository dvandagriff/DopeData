# Copyright 2026 Drew Vandagriff
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without
# limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT. IN NO
# EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN
# AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.

"""Convenience query helpers over a GraphStore."""

from __future__ import annotations

from dopedata.core.graph import GraphStore


def nodes_of_type(store: GraphStore, node_type: str) -> list[dict]:
    """Return all nodes of *node_type* via a minimal Cypher query."""
    cypher = f"MATCH (n:{node_type}) RETURN n"
    results = store.query(cypher)
    return [row.get("n") for row in results if "n" in row and row["n"] is not None]


def edges_of_type(store: GraphStore, rel_type: str) -> list[dict]:
    """Return all edges of *rel_type* via a minimal Cypher query."""
    cypher = f"MATCH ()-[r:{rel_type}]->() RETURN r"
    results = store.query(cypher)
    return [row.get("r") for row in results if "r" in row and row["r"] is not None]


def walk_from(store: GraphStore, start_node_id: str, max_hops: int = 3) -> list[dict]:
    """Walk edges outward from *start_node_id* up to *max_hops* steps.

    Returns a flat list of dicts with keys ``level``, ``node``, and ``edge``.
    """
    visited: set[str] = {start_node_id}
    results: list[dict] = []
    current_level: list[str] = [start_node_id]

    for level in range(1, max_hops + 1):
        next_ids: set[str] = set()
        for node_id in current_level:
            neighbours = store.neighbors(node_id, direction="out")
            for nb in neighbours:
                nb_id = nb.get("id", "")
                if nb_id and nb_id not in visited:
                    visited.add(nb_id)
                    next_ids.add(nb_id)
                    results.append({"level": level, "node": nb, "edge": None})
        current_level = list(next_ids)
        if not current_level:
            break

    return results


def find_stale_nodes(
    store: GraphStore,
    node_type: str,
    stale_prop: str = "stale",
) -> list[dict]:
    """Return nodes of *node_type* where the given property is ``true``."""
    cypher = f"MATCH (n:{node_type}) WHERE n.{stale_prop} = true RETURN n"
    results = store.query(cypher)
    return [row.get("n") for row in results if "n" in row and row["n"] is not None]


__all__: list[str] = [
    "edges_of_type",
    "find_stale_nodes",
    "nodes_of_type",
    "walk_from",
]
