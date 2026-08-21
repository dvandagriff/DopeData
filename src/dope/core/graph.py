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

from __future__ import annotations

import logging
import pickle
import re
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class GraphStore(Protocol):
    """Protocol that all graph backends must implement."""

    def add_node(self, node_type: str, node_id: str, **props: Any) -> None: ...

    def add_edge(
        self, rel_type: str, from_id: str, to_id: str, **props: Any
    ) -> None: ...

    def query(self, cypher: str, **params: Any) -> list[dict]: ...

    def node(self, node_id: str) -> dict | None: ...

    def neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "out",
    ) -> list[dict]: ...

    def save(self, path: str) -> None: ...

    def load(self, path: str) -> None: ...


class PurePyGraph:
    """Zero-dependency in-memory graph backed by dicts. Implements GraphStore."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict] = {}
        self._edges: list[dict] = []

    # ── mutation ───────────────────────────────────────────────────────

    def add_node(self, node_type: str, node_id: str, **props: Any) -> None:
        """Store a node keyed by *node_id*.

        The ``type`` key is normalised to the canonical value string.
        Existing props are shallow-merged; explicit kwargs win on collision.
        """
        self._nodes[node_id] = {"type": node_type, "id": node_id, **props}

    def add_edge(
        self, rel_type: str, from_id: str, to_id: str, **props: Any
    ) -> None:
        """Append a directed edge to the internal list."""
        self._edges.append(
            {
                "rel_type": rel_type,
                "from_id": from_id,
                "to_id": to_id,
                **props,
            }
        )

    # ── look-ups ───────────────────────────────────────────────────────

    def node(self, node_id: str) -> dict | None:
        """Return the node dict for *node_id*, or ``None``."""
        return self._nodes.get(node_id)

    def neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "out",
    ) -> list[dict]:
        """Return neighbour nodes as dicts.

        Parameters
        ----------
        direction : ``"out"`` or ``"in"``
            *``"out"``* – edges where *node_id* is the source.
            *``"in"``*  – edges where *node_id* is the target.
        """
        results: list[dict] = []
        for edge in self._edges:
            if rel_type and edge["rel_type"] != rel_type:
                continue

            src, tgt = edge["from_id"], edge["to_id"]

            if direction == "out" and src == node_id:
                neighbour = self._nodes.get(tgt)
                if neighbour is not None:
                    results.append(neighbour)
            elif direction == "in" and tgt == node_id:
                neighbour = self._nodes.get(src)
                if neighbour is not None:
                    results.append(neighbour)

        return results

    # ── persistence ────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Pickle the entire graph to *path*."""
        with open(path, "wb") as fh:
            pickle.dump({"nodes": self._nodes, "edges": self._edges}, fh)

    def load(self, path: str) -> None:
        """Restore a graph pickled by :meth:`save`."""
        with open(path, "rb") as fh:
            data = pickle.load(fh)  # noqa: S301 — internal binary format
        self._nodes = data["nodes"]
        self._edges = data["edges"]

    # ── Cypher subset query engine ─────────────────────────────────────

    def query(self, cypher: str, **params: Any) -> list[dict]:
        """Execute a minimal subset of Cypher against the in-memory graph.

        Supported patterns (with optional ``WHERE`` clause):

        1. ``MATCH (n:Type) RETURN n``
        2. ``MATCH (a)-[r:REL]->(b) RETURN a, r, b``
        3. ``MATCH (a)-[r:REL]->(b)-[s:REL]->(c) RETURN a, b, c``
        4. Where-clause filters on the above shapes

        Returns a list of dicts with keys matching the RETURN variables.
        """
        cypher = cypher.strip().rstrip(";")
        params = dict(params)

        # ── detect shape ───────────────────────────────────────────
        # Shape 3: two-hop walk (a)-[r]->(b)-[s]->(c)
        match_two_hop = re.match(
            r"(?i)"
            r"MATCH\s+"
            r"\((\w+)\s*:\s*(\w+?)\)\s*"
            r"\[\s*(\w+)\s*:\s*(\w+?)\]\s*->\s*"
            r"\((\w+)\s*:\s*(\w+?)\)\s*"
            r"\[\s*(\w+)\s*:\s*(\w+?)\]\s*->\s*"
            r"\((\w+)\s*:\s*(\w+?)\)"
            r"(?:\s+WHERE\s+(.+?))?"
            r"(?:\s+RETURN\s+(.+))?",
            cypher,
        )
        if match_two_hop:
            return self._query_two_hop(match_two_hop, params)

        # Shape 2: single edge (a)-[r]->(b)
        match_edge = re.match(
            r"(?i)"
            r"MATCH\s+"
            r"\((\w+)\s*:\s*(\w+?)\)\s*"
            r"\[\s*(\w+)\s*:\s*(\w+?)\]\s*->\s*"
            r"\((\w+)\s*:\s*(\w+?)\)"
            r"(?:\s+WHERE\s+(.+?))?"
            r"(?:\s+RETURN\s+(.+))?",
            cypher,
        )
        if match_edge:
            return self._query_edge(match_edge, params)

        # Shape 1: single node (n:Type)
        match_node = re.match(
            r"(?i)"
            r"MATCH\s+"
            r"\((\w+)\s*:\s*(\w+?)\)"
            r"(?:\s+WHERE\s+(.+?))?"
            r"(?:\s+RETURN\s+(.+))?",
            cypher,
        )
        if match_node:
            return self._query_node(match_node, params)

        # Nothing matched — point user to the Kuzu backend.
        msg = (
            f"Unsupported Cypher pattern: {cypher!r}. "
            f"The PurePyGraph supports only single-node, single-edge, and "
            f"two-hop walk patterns with basic WHERE clauses. "
            f"Use the KuzuGraph backend for full Cypher support."
        )
        logger.warning(msg)
        raise NotImplementedError(msg)

    # ── private helpers ────────────────────────────────────────────────

    def _where_filter(
        self, where_clause: str, aliases: set[str], params: dict[str, Any]
    ) -> callable:
        """Build a predicate function from a WHERE clause string."""
        clauses = [c.strip() for c in self._split_where(where_clause)]

        def _check(record: dict) -> bool:
            for clause in clauses:
                if not self._eval_single_where(clause, record, aliases, params):
                    return False
            return True

        return _check

    @staticmethod
    def _split_where(raw: str) -> list[str]:
        """Split a WHERE clause on AND / OR while respecting parens."""
        depth = 0
        parts: list[str] = []
        current: list[str] = []
        tokens = raw.split()
        for token in tokens:
            depth += token.count("(") - token.count(")")
            current.append(token)
            if depth <= 0 and token.upper().rstrip(";") in ("AND", "OR"):
                parts.append(" ".join(current).strip())
                current = []
                depth = max(depth, 0)
        leftover = " ".join(current).strip()
        if leftover:
            parts.append(leftover)
        return [p for p in parts if p and not p.upper().startswith(("AND", "OR"))]

    def _eval_single_where(
        self,
        clause: str,
        record: dict,
        aliases: set[str],
        params: dict[str, Any],
    ) -> bool:
        """Evaluate one atomic WHERE clause like ``n.id = $id``."""
        clause = clause.strip().rstrip(";")

        # Try parameter reference:  n.prop = $param
        m_param = re.match(
            r"(\w+)\.(\w+)\s*=\s*\$(\w+)", clause
        )
        if m_param:
            alias, prop, param_name = m_param.groups()
            value = self._get_field(alias, prop, record, aliases)
            expected = params.get(param_name)
            return value == expected

        # Boolean literal:  n.stale = true  /  n.stale = false
        m_bool = re.match(
            r"(\w+)\.(\w+)\s*=\s*(true|false)", clause, re.IGNORECASE
        )
        if m_bool:
            alias, prop, lit = m_bool.groups()
            value = self._get_field(alias, prop, record, aliases)
            expected = lit.lower() == "true"
            return value == expected

        # String literal:  n.name = 'something'  (or double-quoted)
        m_str = re.match(
            r"(\w+)\.(\w+)\s*=\s*'([^']*)'", clause
        )
        if m_str:
            alias, prop, expected = m_str.groups()
            value = self._get_field(alias, prop, record, aliases)
            return value == expected

        # Numeric literal:  n.row_count > 100
        m_cmp = re.match(
            r"(\w+)\.(\w+)\s*([><=!]+)\s*(.+)", clause
        )
        if m_cmp:
            alias, prop, op, operand = m_cmp.groups()
            value = self._get_field(alias, prop, record, aliases)
            operand = operand.strip().strip("'\"")
            try:
                expected = int(operand)
            except ValueError:
                try:
                    expected = float(operand)
                except ValueError:
                    expected = operand
            return self._cmp(value, op, expected)

        logger.warning("Unparsed WHERE clause: %s", clause)
        return True  # best-effort: don't drop rows for unparseable filters

    @staticmethod
    def _cmp(left: Any, op: str, right: Any) -> bool:
        if left is None:
            return False
        op = op.strip()
        if op == "=" or op == "==":
            return left == right
        if op == "!=" or op == "<>":
            return left != right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        return False

    def _get_field(
        self, alias: str, prop: str, record: dict, aliases: set[str]
    ) -> Any:
        """Pull a field value from the current MATCH record by variable alias."""
        if alias in record:
            obj = record[alias]
            if isinstance(obj, dict):
                return obj.get(prop)
        return None

    def _resolve_aliases(
        self, names_spec: str, aliases: list[str], records: list[dict]
    ) -> list[dict]:
        """Filter each row to only the requested RETURN columns."""
        tokens = [t.strip() for t in names_spec.split(",")]
        rows: list[dict] = []
        for record in records:
            out: dict[str, Any] = {}
            for token in tokens:
                if token == "*":
                    out.update(record)
                else:
                    name = token.strip()
                    if name in record:
                        out[name] = record[name]
                    else:
                        # Could be just the alias without explicit name
                        out[name] = record.get(name)
            rows.append(out)
        return rows

    def _query_node(
        self, match: re.Match, params: dict[str, Any]
    ) -> list[dict]:
        """Shape 1: MATCH (n:Type) RETURN ..."""
        alias = match.group(1)
        node_type = match.group(2)
        where_str = match.group(3)
        return_spec = match.group(4)

        aliases = {alias}
        predicate = self._where_filter(where_str, aliases, params) if where_str else lambda r: True

        results: list[dict] = []
        for node_id, data in self._nodes.items():
            if data.get("type") != node_type:
                continue
            record = {alias: data}
            if predicate(record):
                row = self._resolve_aliases(return_spec, [alias], [record])
                results.extend(row)

        return results

    def _query_edge(
        self, match: re.Match, params: dict[str, Any]
    ) -> list[dict]:
        """Shape 2: MATCH (a)-[r:REL]->(b) RETURN a, r, b."""
        a_alias = match.group(1)
        a_type = match.group(2)
        r_alias = match.group(3)
        r_type = match.group(4)
        b_alias = match.group(5)
        b_type = match.group(6)
        where_str = match.group(7)
        return_spec = match.group(8)

        aliases = {a_alias, r_alias, b_alias}
        predicate = self._where_filter(where_str, aliases, params) if where_str else lambda r: True

        results: list[dict] = []
        for edge in self._edges:
            if r_type and edge["rel_type"] != r_type:
                continue
            src_node = self._nodes.get(edge["from_id"])
            dst_node = self._nodes.get(edge["to_id"])
            if src_node is None or dst_node is None:
                continue
            if a_type and src_node.get("type") != a_type:
                continue
            if b_type and dst_node.get("type") != b_type:
                continue
            record = {
                a_alias: src_node,
                r_alias: edge,
                b_alias: dst_node,
            }
            if predicate(record):
                row = self._resolve_aliases(return_spec, list(aliases), [record])
                results.extend(row)

        return results

    def _query_two_hop(
        self, match: re.Match, params: dict[str, Any]
    ) -> list[dict]:
        """Shape 3: MATCH (a)-[r]->(b)-[s]->(c) RETURN a, b, c."""
        a_alias = match.group(1)
        a_type = match.group(2)
        r_alias = match.group(3)
        r_type = match.group(4)
        b_alias = match.group(5)
        b_type = match.group(6)
        s_alias = match.group(7)
        s_type = match.group(8)
        c_alias = match.group(9)
        c_type = match.group(10)
        where_str = match.group(11)
        return_spec = match.group(12)

        aliases = {a_alias, r_alias, b_alias, s_alias, c_alias}
        predicate = self._where_filter(where_str, aliases, params) if where_str else lambda r: True

        results: list[dict] = []
        for e1 in self._edges:
            if r_type and e1["rel_type"] != r_type:
                continue
            mid_node = self._nodes.get(e1["to_id"])
            if mid_node is None:
                continue
            if b_type and mid_node.get("type") != b_type:
                continue

            for e2 in self._edges:
                if s_type and e2["rel_type"] != s_type:
                    continue
                if e2["from_id"] != e1["to_id"]:
                    continue
                end_node = self._nodes.get(e2["to_id"])
                if end_node is None:
                    continue
                if c_type and end_node.get("type") != c_type:
                    continue

                start_node = self._nodes.get(e1["from_id"])
                if start_node is None:
                    continue
                if a_type and start_node.get("type") != a_type:
                    continue

                record = {
                    a_alias: start_node,
                    r_alias: e1,
                    b_alias: mid_node,
                    s_alias: e2,
                    c_alias: end_node,
                }
                if predicate(record):
                    row = self._resolve_aliases(return_spec, list(aliases), [record])
                    results.extend(row)

        return results
