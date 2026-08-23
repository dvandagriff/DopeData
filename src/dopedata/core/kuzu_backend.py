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

"""Guarded Kùzu graph backend.

Kùzu must be installed separately (``pip install kuzu``).  When absent, all
instantiation attempts raise :class:`NotImplementedError` with a helpful message.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

try:
    import kuzu

    KUZU_AVAILABLE = True
except ImportError:  # pragma: no cover
    KUZU_AVAILABLE = False  # type: ignore[assignment]

from dopedata.core.graph import GraphStore
from dopedata.core.schema import CYPHER_DDL

logger = logging.getLogger(__name__)


# ── Stub classes when Kùzu is unavailable ────────────────────────────


class _KuzuGraphUnavailable(GraphStore):
    """Raises ``NotImplementedError`` so the caller learns kuzu is missing."""

    def __init__(self, db_path: str = ":memory:") -> None:
        raise NotImplementedError(
            "kuzu is not installed. Install it with `pip install kuzu` to use "
            "the Kùzu backend."
        )

    def add_node(self, node_type: str, node_id: str, **props: Any) -> None:
        raise NotImplementedError("Kùzu backend unavailable")

    def add_edge(
        self, rel_type: str, from_id: str, to_id: str, **props: Any
    ) -> None:
        raise NotImplementedError("Kùzu backend unavailable")

    def query(self, cypher: str, **params: Any) -> list[dict]:
        raise NotImplementedError("Kùzu backend unavailable")

    def node(self, node_id: str) -> dict | None:
        raise NotImplementedError("Kùzu backend unavailable")

    def neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "out",
    ) -> list[dict]:
        raise NotImplementedError("Kùzu backend unavailable")

    def save(self, path: str) -> None:
        raise NotImplementedError("Kùzu backend unavailable")

    def load(self, path: str) -> None:
        raise NotImplementedError("Kùzu backend unavailable")


# ── Real Kùzu-backed implementation ──────────────────────────────────


class KuzuGraph(GraphStore):
    """GraphStore backed by an on-disk or in-memory Kùzu database.

    Parameters
    ----------
    db_path :
        Filesystem path to the ``.db`` file, or ``":memory:"`` for ephemeral storage.
    recreate :
        If ``True``, drop existing tables and re-run CYPHER_DDL on construction.
    """

    def __init__(self, db_path: str = ":memory:", recreate: bool = False) -> None:  # noqa: ARG002
        self._db_path = db_path
        self._db = kuzu.Database(db_path)
        self._con = kuzu.Connection(self._db)
        self._initialized = not recreate and self._tables_exist()

        if not self._initialized:
            self._init_schema()

    # ── internal helpers ─────────────────────────────────────────────

    def _tables_exist(self) -> bool:
        """Best-effort check whether CYPHER_DDL has already been run."""
        try:
            result = self._con.execute("SHOW TABLES;")
            rows = [row.to_list() for row in result]
            table_names = {r[0] for r in rows}
            return len(table_names) >= 6
        except Exception:
            return False

    def _init_schema(self) -> None:
        """Execute the full CYPHER_DDL script."""
        statements = [s.strip() for s in CYPHER_DDL.split(";") if s.strip()]
        for stmt in statements:
            logger.debug("DDL: %s", stmt[:120])
            self._con.execute(stmt)

    def _get_node_tables(self) -> list[str]:
        """Return names of all node tables in the database."""
        result = self._con.execute("SHOW TABLES;")
        tables: list[str] = []
        for row in result:
            entry = row.to_list()[0]
            if not entry.startswith("__index__"):
                tables.append(entry)
        return tables

    @staticmethod
    def _node_from_type(rel_type: str) -> str:
        """Best-effort heuristic for inferring source node table from relation name."""
        known_edges: dict[str, tuple[str, str]] = {
            "SYNC_TO": ("FivetranConnection", "SnowflakeTable"),
            "PRODUCES": ("dbtModel", "SnowflakeTable"),
            "DEPENDS_ON": ("dbtModel", "dbtModel"),
            "TESTS": ("dbtTest", "dbtModel"),
            "FEEDS": ("SnowflakeTable", "DataProduct"),
            "EXPOSED_BY": ("DataProduct", "dbtModel"),
        }
        src, _ = known_edges.get(rel_type, ("UnknownNode", "UnknownNode"))
        return src

    @staticmethod
    def _node_to_type(rel_type: str) -> str:
        """Best-effort heuristic for inferring target node table from relation name."""
        known_edges: dict[str, tuple[str, str]] = {
            "SYNC_TO": ("FivetranConnection", "SnowflakeTable"),
            "PRODUCES": ("dbtModel", "SnowflakeTable"),
            "DEPENDS_ON": ("dbtModel", "dbtModel"),
            "TESTS": ("dbtTest", "dbtModel"),
            "FEEDS": ("SnowflakeTable", "DataProduct"),
            "EXPOSED_BY": ("DataProduct", "dbtModel"),
        }
        _, tgt = known_edges.get(rel_type, ("UnknownNode", "UnknownNode"))
        return tgt

    # ── GraphStore API ───────────────────────────────────────────────

    def add_node(self, node_type: str, node_id: str, **props: Any) -> None:
        """Insert or upsert a node."""
        table_name = node_type
        normalised_props = {k: self._normalise(v) for k, v in props.items()}

        # Try to ensure the table exists
        col_defs = ["id STRING PRIMARY KEY"] + [
            f"{k} {self._type_to_kuzu(type(normalised_props[k]))}"
            for k in normalised_props
            if k != "id"
        ]
        create_stmt = (
            f"CREATE NODE TABLE {table_name}({', '.join(col_defs)}) UNIQUE(id);"
        )
        try:
            self._con.execute(create_stmt)
        except Exception:
            pass  # Table already exists

        insert_cols = "id," + ",".join(k for k in normalised_props if k != "id")
        placeholders = "$" + ",$".join(normalised_props.keys())
        values_list = [v for v in normalised_props.values()]
        self._con.execute(
            f"INSERT INTO {table_name}({insert_cols}) VALUES({placeholders});",
            values_list,
        )

    def add_edge(
        self, rel_type: str, from_id: str, to_id: str, **props: Any
    ) -> None:
        """Insert a directed relation edge."""
        table_name = rel_type
        normalised_props = {k: self._normalise(v) for k, v in props.items()}

        # Ensure the relation table exists first.
        try:
            src_table = self._node_from_type(rel_type)
            dst_table = self._node_to_type(rel_type)
            self._con.execute(
                f"CREATE REL TABLE {table_name} "
                f"(FROM {src_table} TO {dst_table});"
            )
        except Exception:
            pass

        insert_cols = "src, dst"
        placeholders = "$src,$dst"
        values_list: list[Any] = [from_id, to_id]

        if normalised_props:
            col_names = ",".join(k for k in normalised_props)
            ph_values = ",".join(f"${k}" for k in normalised_props)
            insert_cols += f",{col_names}"
            placeholders += f",{ph_values}"
            values_list.extend(normalised_props.values())

        self._con.execute(
            f"INSERT INTO {table_name}({insert_cols}) VALUES({placeholders});",
            values_list,
        )

    def query(self, cypher: str, **params: Any) -> list[dict]:
        """Execute arbitrary Cypher against the Kùzu database."""
        result = self._con.execute(cypher, params)
        columns = result.columns
        rows: list[dict] = []
        for row in result:
            record: dict[str, Any] = {}
            for col, val in zip(columns, row.to_list()):
                record[col] = val
            rows.append(record)
        return rows

    def node(self, node_id: str) -> dict | None:
        """Look up a single node by its primary key *node_id*.

        Scans all node tables — returns the first match or ``None``.
        """
        tables = self._get_node_tables()
        for table in tables:
            query = f"MATCH (n:{table}) WHERE n.id = $id RETURN n LIMIT 1;"
            result = self._con.execute(query, {"id": node_id})
            for row in result:
                return dict(row.to_list()[0].to_dict()) if row else None
        return None

    def neighbors(
        self,
        node_id: str,
        rel_type: str | None = None,
        direction: str = "out",
    ) -> list[dict]:
        """Return neighbour node dicts."""
        all_neighbors: dict[str, dict] = {}
        result = self._con.execute(
            """MATCH (n {id: $nid})
               OPTIONAL MATCH (n)-[r]->(out_node)
               OPTIONAL MATCH (n)<-[r2]-(in_node)
               RETURN out_node, in_node;""",
            {"nid": node_id},
        )
        for row in result:
            values = row.to_list()
            if direction == "out" and values[0]:
                key = str(values[0]["id"])
                all_neighbors[key] = dict(values[0].to_dict())
            elif direction == "in" and values[1]:
                key = str(values[1]["id"])
                all_neighbors[key] = dict(values[1].to_dict())

        return list(all_neighbors.values())

    def save(self, path: str) -> None:
        """Kùzu databases are persisted on every write.  Copy the .db file."""
        dst = Path(path)
        src = Path(self._db_path)
        if not src.exists():
            raise FileNotFoundError(f"Kùzu DB file not found: {src}")
        shutil.copy2(src, dst)

    def load(self, path: str) -> None:
        """Re-initialise the connection to an existing on-disk database."""
        self._con = None
        self._db = kuzu.Database(str(path))
        self._con = kuzu.Connection(self._db)

    # ── private helpers ───────────────────────────────────────────────

    def _upsert_node(
        self, table_name: str, node_id: str, props: dict[str, Any]
    ) -> None:
        """Update existing node columns."""
        set_clauses = [f"{k} = ${k}" for k in props if k != "id"]
        if not set_clauses:
            return
        set_clause = ", ".join(set_clauses)
        query = f"UPDATE {table_name} SET {set_clause} WHERE id = $id;"
        values = [props[k] for k in props if k != "id"] + [node_id]
        self._con.execute(query, values)

    @staticmethod
    def _normalise(value: Any) -> Any:
        """Convert Python types to Kùzu-friendly primitives."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float, str)):
            return value
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _type_to_kuzu(value_type: type) -> str:
        """Map a Python type to the nearest Kùzu column type string."""
        mapping = {
            int: "INT64",
            float: "FLOAT64",
            str: "STRING",
            bool: "BOOL",
        }
        return mapping.get(value_type, "STRING")


# ── Public factory function ──────────────────────────────────────────


def get_graph_store(
    backend: str = "purepy",
    db_path: str = ":memory:",
    recreate: bool = False,
) -> GraphStore:
    """Return a :class:`GraphStore` implementation.

    Parameters
    ----------
    backend : ``"purepy"``, ``"kuzu"``, or ``"auto"``.
    db_path : Passed to the Kùzu constructor when *backend* is ``"kuzu"``.
    recreate : Rebuild schema on construction when *backend* is ``"kuzu"``.
    """
    if backend == "purepy":
        from dopedata.core.graph import PurePyGraph

        return PurePyGraph()

    if backend == "kuzu":
        if not KUZU_AVAILABLE:
            raise NotImplementedError(
                "kuzu is not installed. Install it with `pip install kuzu` "
                "or use backend='purepy'."
            )
        return KuzuGraph(db_path=db_path, recreate=recreate)

    if backend == "auto":
        if KUZU_AVAILABLE:
            return KuzuGraph(db_path=db_path, recreate=recreate)
        logger.info("Kùzu not available; falling back to PurePyGraph.")
        from dopedata.core.graph import PurePyGraph

        return PurePyGraph()

    raise ValueError(f"Unknown backend: {backend!r}")
