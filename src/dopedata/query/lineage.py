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

"""Seeded walk through the pipeline lineage graph."""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from dopedata.core.freshness import is_stale
from dopedata.core.schema import NodeType

if TYPE_CHECKING:
    from dopedata.core.graph import GraphStore

logger = logging.getLogger(__name__)


def seed_walk(
    store: GraphStore,
    seed_connector_id: str,
    depth_up: int = 3,
    depth_down: int = 3,
    backend: str = "pure",
) -> dict[str, Any]:
    """Walk from a Fivetran connector ID through the lineage graph.

    Direction and edge types::

        UP:   FIVETRAN_CONNECTION <-[SYNC_TO]- SNOWFLAKE_TABLE
        DOWN: SNOWFLAKE_TABLE ->[PRODUCES]- DBT_MODEL ->[DEPENDS_ON]- DBT_MODEL...
              Also pull DBT_TEST nodes for any model in the walk.

    Parameters
    ----------
    store :
        A :class:`GraphStore` implementation.
    seed_connector_id :
        The ID of the starting FIVETRAN_CONNECTION node.
    depth_up :
        How many levels to traverse upward from the seed connector.
    depth_down :
        How many levels to traverse downward from the snowflake tables.
    backend :
        ``"pure"`` for BFS over neighbors API, or ``"kuzu"`` for Cypher.

    Returns
    -------
    dict
        ``{'nodes': [...], 'edges': [...], 'stale_count': int}``
    """
    if backend == "kuzu":
        return _seed_walk_kuzu(store, seed_connector_id, depth_up, depth_down)
    return _seed_walk_pure(store, seed_connector_id, depth_up, depth_down)


# ── pure BFS implementation ───────────────────────────────────────────

def _seed_walk_pure(
    store: GraphStore,
    seed_connector_id: str,
    depth_up: int,
    depth_down: int,
) -> dict[str, Any]:
    """Pure-Python BFS walk over the :meth:`GraphStore.neighbors` API."""

    # Step 1: Verify the seed connector exists
    seed_node = store.node(seed_connector_id)
    if seed_node is None:
        logger.warning("Seed connector %s not found in graph.", seed_connector_id)
        return {"nodes": [], "edges": [], "stale_count": 0}

    collected_nodes: dict[str, dict] = {}
    collected_edges: dict[tuple[str, str, str], dict] = {}

    # Seed the connector node itself
    _collect_node(collected_nodes, seed_connector_id, seed_node)

    stale_count = 0
    if is_stale(_get_stale_property(seed_node)):
        stale_count += 1

    # ── UPWARD: FIVETRAN_CONNECTION → SYNC_TO → SNOWFLAKE_TABLE ──────
    up_visited: set[str] = {seed_connector_id}
    current_level_ids: list[str] = [seed_connector_id]

    for _depth in range(depth_up):
        if not current_level_ids:
            break
        next_ids: set[str] = set()
        for node_id in current_level_ids:
            # Get outgoing SYNC_TO edges → SNOWFLAKE_TABLEs
            neighbors = store.neighbors(node_id, rel_type="SYNC_TO", direction="out")
            for nb in neighbors:
                nb_id = nb.get("id", "")
                if not nb_id or nb_id in up_visited:
                    continue
                up_visited.add(nb_id)
                _collect_node(collected_nodes, nb_id, nb)
                _collect_edge(
                    collected_edges, "SYNC_TO", node_id, nb_id
                )
                next_ids.add(nb_id)

                if is_stale(_get_stale_property(nb)):
                    stale_count += 1

        current_level_ids = list(next_ids)

    # ── DOWNWARD: from SNOWFLAKE_TABLEs through PRODUCES & DEPENDS_ON ─
    down_visited: set[str] = set(up_visited)

    # Start downward walk from snowflake tables only (skip the connector)
    sf_tables = [nid for nid in up_visited if nid != seed_connector_id]
    down_current: list[str] = sf_tables if sf_tables else []

    actual_down = max(0, depth_down)

    step_count = 0
    while down_current and step_count < actual_down:
        next_ids: set[str] = set()
        for node_id in down_current:
            # Check if this is a SnowflakeTable — look for PRODUCES edges coming IN
            # (edges go dbtModel → SnowflakeTable, so we follow "in" direction)
            nb_node = collected_nodes.get(node_id)
            if nb_node and nb_node.get("type") == NodeType.SNOWFLAKE_TABLE.value:
                producing_models = store.neighbors(node_id, rel_type="PRODUCES", direction="in")
                for nb in producing_models:
                    delta, added_ids = _process_downward_neighbor(
                        nb, next_ids, down_visited, collected_nodes, collected_edges,
                        "PRODUCES", node_id,
                    )
                    stale_count += delta
                    next_ids.update(added_ids)

            # DEPENDS_ON edges go FROM model TO its dependency, so follow "out" from any model
            if nb_node and nb_node.get("type") == NodeType.DBT_MODEL.value:
                deps = store.neighbors(node_id, rel_type="DEPENDS_ON", direction="out")
                for nb in deps:
                    delta, added_ids = _process_downward_neighbor(
                        nb, next_ids, down_visited, collected_nodes, collected_edges,
                        "DEPENDS_ON", node_id,
                    )
                    stale_count += delta
                    next_ids.update(added_ids)

        down_current = list(next_ids)
        step_count += 1

    # ── Find TESTS edges pointing to any model in the walk ─────────────
    for nid, node_dict in list(collected_nodes.items()):
        if node_dict.get("type") == NodeType.DBT_MODEL.value:
            # Look up the latest stored version
            current = store.node(nid)
            if current is None:
                continue
            tests = store.neighbors(nid, rel_type="TESTS", direction="in")
            for test_nb in tests:
                test_id = test_nb.get("id", "")
                if not test_id:
                    continue
                _collect_node(collected_nodes, test_id, test_nb)
                _collect_edge(
                    collected_edges, "TESTS", test_id, nid
                )
                if is_stale(_get_stale_property(test_nb)):
                    stale_count += 1

    return {
        "nodes": list(collected_nodes.values()),
        "edges": list(collected_edges.values()),
        "stale_count": stale_count,
    }


def _process_downward_neighbor(
    nb: dict,
    next_ids: set[str],
    down_visited: set[str],
    collected_nodes: dict[str, dict],
    collected_edges: dict[tuple[str, str, str], dict],
    rel_type: str,
    parent_id: str,
) -> tuple[int, set[str]]:
    """Helper to add a downstream neighbor node and its edge.

    Returns (stale_delta, new_ids) where stale_delta is 0 or 1.

    The *rel_type* determines the actual edge direction in the graph:
      - ``"PRODUCES"`` edges are stored as dbtModel → SnowflakeTable,
        so traversing from a table via ``direction="in"`` means the edge
        should be recorded as (neighbor, parent).
      - ``"DEPENDS_ON"`` edges are stored as model → dependency,
        so traversing from a model via ``direction="out"`` means the edge
        should be recorded as (parent, neighbor).
    """
    nb_id = nb.get("id", "")
    if not nb_id or nb_id in down_visited:
        return 0, set()
    down_visited.add(nb_id)
    _collect_node(collected_nodes, nb_id, nb)

    # Edge direction depends on relation type (graph schema convention)
    if rel_type == "PRODUCES":
        # Stored as dbtModel → SnowflakeTable; we found model via "in" from table
        edge_from, edge_to = nb_id, parent_id
    else:
        # DEPENDS_ON: stored as model → dependency; we found dep via "out" from model
        edge_from, edge_to = parent_id, nb_id

    _collect_edge(collected_edges, rel_type, edge_from, edge_to)
    stale_delta = 1 if is_stale(_get_stale_property(nb)) else 0
    next_ids.add(nb_id)
    return stale_delta, {nb_id}


def _collect_node(
    collected: dict[str, dict], node_id: str, node_dict: dict
) -> None:
    """Add a node to the collected set if not already present."""
    if node_id not in collected:
        # Build a minimal representation for output
        entry = {
            "id": node_id,
            "type": node_dict.get("type", ""),
        }
        for key in ("name", "schema", "status", "freshness", "stale",
                     "row_count", "materialization", "owner"):
            if key in node_dict:
                entry[key] = node_dict[key]
        collected[node_id] = entry


def _collect_edge(
    collected: dict[tuple[str, str, str], dict],
    rel_type: str,
    from_id: str,
    to_id: str,
) -> None:
    """Add an edge to the collected set if not already present."""
    key = (rel_type, from_id, to_id)
    if key not in collected:
        collected[key] = {
            "rel_type": rel_type,
            "from_id": from_id,
            "to_id": to_id,
        }


def _get_stale_property(node: dict) -> datetime.date | datetime.datetime | None:
    """Extract a date-like value from a node for staleness checks."""
    for key in ("last_modified", "end_time", "last_sync_end", "finished_at"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            try:
                return _parse_iso_date(val)
            except (ValueError, TypeError):
                continue
        elif val is not None and (isinstance(val, datetime.date) or isinstance(val, datetime.datetime)):
            return val
    return None


def _parse_iso_date(value: str) -> datetime.date | datetime.datetime:
    """Parse a date/datetime string."""
    value = value.strip().rstrip("Z")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {value!r}")


# ── Kùzu Cypher implementation ───────────────────────────────────────


def _collect_node_kuzu(
    collected: dict[str, dict], node_id: str, node_dict: dict
) -> None:
    """Add a node to the collected set if not already present (Kùzu backend)."""
    if node_id not in collected:
        entry = {
            "id": node_id,
            "type": node_dict.get("type", ""),
        }
        for key in ("name", "schema", "status", "freshness", "stale",
                     "row_count", "materialization", "owner"):
            if key in node_dict:
                entry[key] = node_dict[key]
        collected[node_id] = entry


def _collect_edge_kuzu(
    collected: dict[tuple[str, str, str], dict],
    rel_type: str,
    from_id: str,
    to_id: str,
) -> None:
    """Add an edge to the collected set if not already present (Kùzu backend)."""
    key = (rel_type, from_id, to_id)
    if key not in collected:
        collected[key] = {
            "rel_type": rel_type,
            "from_id": from_id,
            "to_id": to_id,
        }


def _seed_walk_kuzu(
    store: GraphStore,
    seed_connector_id: str,
    depth_up: int,
    depth_down: int,
) -> dict[str, Any]:
    """Walk using full Cypher support via Kùzu."""

    # Verify seed node exists
    seed_node = store.node(seed_connector_id)
    if seed_node is None:
        logger.warning("Seed connector %s not found in graph.", seed_connector_id)
        return {"nodes": [], "edges": [], "stale_count": 0}

    up_limit = max(depth_up, 1)
    down_limit = max(depth_down, 1)

    # Cypher query to walk from the seed connector through the lineage graph
    cypher = f"""\
MATCH (c:FivetranConnection {{id: $seed_id}})
OPTIONAL MATCH path_up = (c)<-[:SYNC_TO*1..{up_limit}]-(sf:SnowflakeTable)
WITH sf, collect(sf) AS sftables
UNWIND sftables AS sf2
OPTIONAL MATCH path_down = (sf2)-[:PRODUCES|DEPENDS_ON*1..{down_limit}]->(m:dbtModel)
WITH collect(DISTINCT c) AS connectors,
     collect(DISTINCT sf2) AS tables,
     collect(DISTINCT m) AS models
RETURN connectors, tables, models
"""

    results = store.query(cypher, seed_id=seed_connector_id)

    nodes_map: dict[str, dict] = {}
    edges_map: dict[tuple[str, str, str], dict] = {}
    stale_count = 0

    # Extract all nodes from result rows
    for row in results:
        # FivetranConnection nodes
        for conn in (row.get("connectors") or []):
            if isinstance(conn, dict) and "id" in conn:
                _collect_node_kuzu(nodes_map, str(conn["id"]), dict(conn))

        # SnowflakeTable nodes
        for sf in (row.get("tables") or []):
            if isinstance(sf, dict) and "id" in sf:
                _collect_node_kuzu(nodes_map, str(sf["id"]), dict(sf))

        # dbtModel nodes
        for model in (row.get("models") or []):
            if isinstance(model, dict) and "id" in model:
                _collect_node_kuzu(nodes_map, str(model["id"]), dict(model))

    # Now run additional queries to gather edges and test relationships
    # SYNC_TO edges from the connector
    sync_edges = store.query(
        f"MATCH (c:FivetranConnection {{id: $seed_id}})-[r:SYNC_TO]->(t:SnowflakeTable) "
        f"RETURN t, r",
        seed_id=seed_connector_id,
    )
    for row in sync_edges:
        sf = row.get("t")
        rel = row.get("r") or {}
        if isinstance(sf, dict):
            sid = str(sf.get("id", ""))
            eid = rel.get("src_id", "")
            tid = rel.get("dst_id", "")
            _collect_edge_kuzu(edges_map, "SYNC_TO", tid or eid, sid)

    # PRODUCES edges from snowflake tables to models
    if nodes_map:
        table_ids_str = ", ".join(f"'{tid}'" for tid in nodes_map)
        produces_query = f"""\
MATCH (m:dbtModel)-[r:PRODUCES]->(sf:SnowflakeTable)
WHERE sf.id IN [{table_ids_str}]
RETURN m, sf, r;"""
        try:
            prod_results = store.query(produces_query)
            for row in prod_results:
                model = row.get("m")
                sf = row.get("sf")
                if isinstance(model, dict) and isinstance(sf, dict):
                    mid = str(model["id"])
                    sfid = str(sf["id"])
                    _collect_node_kuzu(nodes_map, mid, dict(model))
                    _collect_edge_kuzu(edges_map, "PRODUCES", mid, sfid)
        except Exception:  # pragma: no cover – Kuzu errors only
            pass

    # DEPENDS_ON edges between models
    model_ids_str = ", ".join(
        f"'{mid}'" for mid, nd in nodes_map.items()
        if nd.get("type") == "dbtModel"
    )
    if model_ids_str:
        deps_query = f"""\
MATCH (a:dbtModel)-[r:DEPENDS_ON]->(b:dbtModel)
WHERE a.id IN [{model_ids_str}] OR b.id IN [{model_ids_str}]
RETURN a, b;"""
        try:
            deps_results = store.query(deps_query)
            for row in deps_results:
                a_node = row.get("a")
                b_node = row.get("b")
                if isinstance(a_node, dict):
                    aid = str(a_node["id"])
                    _collect_node_kuzu(nodes_map, aid, dict(a_node))
                if isinstance(b_node, dict):
                    bid = str(b_node["id"])
                    _collect_node_kuzu(nodes_map, bid, dict(b_node))
                if isinstance(a_node, dict) and isinstance(b_node, dict):
                    _collect_edge_kuzu(edges_map, "DEPENDS_ON", a_node["id"], b_node["id"])
        except Exception:  # pragma: no cover
            pass

    # TESTS edges pointing to models
    for mid in [nid for nid, nd in nodes_map.items() if nd.get("type") == "dbtModel"]:
        test_edges = store.query(
            f"MATCH (t:dbtTest)-[r:TESTS]->(m:dbtModel {{id: $model_id}}) RETURN t;",
            model_id=mid,
        )
        for row in test_edges:
            test_node = row.get("t")
            if isinstance(test_node, dict):
                tid = str(test_node["id"])
                _collect_node_kuzu(nodes_map, tid, dict(test_node))
                _collect_edge_kuzu(edges_map, "TESTS", tid, mid)

    # Count stale nodes
    for node_id, node_dict in nodes_map.items():
        stale_val = node_dict.get("stale")
        if stale_val is True:
            stale_count += 1
        elif stale_val is None and not stale_val:
            # Check if we can compute freshness
            last_mod = node_dict.get("last_modified") or node_dict.get("end_time")
            if last_mod is None:
                stale_count += 1

    return {
        "nodes": list(nodes_map.values()),
        "edges": list(edges_map.values()),
        "stale_count": stale_count,
    }
