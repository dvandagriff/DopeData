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

"""Fivetran plugin – ingest connector & schema snapshot data into the graph."""

from __future__ import annotations

import csv
import datetime
import json
import logging
import os
import pathlib
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

from dopedata.core.freshness import freshness_date, is_stale
from dopedata.core.plugin import PipelinePlugin
from dopedata.core.schema import NodeType

if TYPE_CHECKING:
    from dopedata.core.graph import GraphStore

logger = logging.getLogger(__name__)

_SNAPSHOT_DIR_ENV = "DOPE_SNAPSHOT_DIR"
_DEFAULT_SNAPSHOTS_DIR = pathlib.Path("data/snapshots")


def _resolve_snapshot_dir() -> pathlib.Path:
    """Return the directory containing snapshot CSV/JSON files."""
    env_val = os.environ.get(_SNAPSHOT_DIR_ENV)
    if env_val:
        return pathlib.Path(env_val)
    # Resolve relative to project root (parent of src/)
    candidate = pathlib.Path(__file__).resolve().parents[3] / "data" / "snapshots"
    if candidate.exists():
        return candidate
    # Fallback current working directory
    return pathlib.Path.cwd() / "data" / "snapshots"


class FivetranPlugin(PipelinePlugin):
    """Ingest Fivetran connector metadata into a :class:`GraphStore`.

    Supports two ingestion modes:

    * **snapshot** (default) – reads CSV files from the snapshot directory.
    * **live** – queries the Fivetran REST API.
    """

    def __init__(self, snapshot_dir: pathlib.Path | None = None) -> None:
        """Initialise with an optional snapshot directory override."""
        self.snapshot_dir: pathlib.Path | None = snapshot_dir

    # ── public API ──────────────────────────────────────────────────────

    def ingest(
        self,
        store: GraphStore,
        mode: str = "snapshot",
        **kwargs: Any,
    ) -> int:
        """Ingest Fivetran data into *store*.

        Parameters
        ----------
        store :
            The graph store to populate.
        mode :
            ``"snapshot"`` (CSV files) or ``"live"`` (REST API).
        snapshot_dir :
            Override the default snapshot directory path.
        **kwargs :
            Ignored.

        Returns
        -------
        int
            Number of nodes created.
        """
        snap_dir = (
            kwargs.get("snapshot_dir") or self.snapshot_dir or _resolve_snapshot_dir()
        )

        if mode == "live":
            try:
                return self._ingest_live(store)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Live ingestion failed (%s), falling back to snapshot mode.", exc
                )
                return self._ingest_snapshot(store, snap_dir)

        return self._ingest_snapshot(store, snap_dir)

    # ── snapshot mode ───────────────────────────────────────────────────

    def _ingest_snapshot(self, store: GraphStore, snapshot_dir: pathlib.Path) -> int:
        """Read CSV files and build the graph from them."""
        connections_path = snapshot_dir / "fivetran_connections.csv"
        schemas_path = snapshot_dir / "fivetran_schemas.csv"
        bridge_path = snapshot_dir / "fivetran_dbt_bridge.csv"

        # Load CSVs
        connections = self._read_csv(connections_path)
        schemas = self._read_csv(schemas_path)
        bridges = self._read_csv(bridge_path)

        node_count = 0

        # Index schemas by connector_id
        schemas_by_connector: dict[str, list[dict]] = {}
        for schema_row in schemas:
            cid = schema_row.get("connector_id", "")
            schemas_by_connector.setdefault(cid, []).append(schema_row)

        # Index bridges by connector_id
        bridges_by_connector: dict[str, list[dict]] = {}
        for bridge_row in bridges:
            cid = bridge_row.get("connector_id", "")
            bridges_by_connector.setdefault(cid, []).append(bridge_row)

        # Build a mapping from (connector_id, schema, table) → rows_synced info
        # We need to track the last_sync_end and rows_synced per connector
        conn_info: dict[str, dict[str, Any]] = {}
        for conn_row in connections:
            cid = conn_row.get("connector_id", "")
            if not cid:
                continue
            conn_info[cid] = {
                "name": conn_row.get("name", ""),
                "status": conn_row.get("status", ""),
                "last_sync_start": conn_row.get("last_sync_start", ""),
                "last_sync_end": conn_row.get("last_sync_end", ""),
                "rows_synced": conn_row.get("rows_synced", ""),
            }

        # 1. Create FIVETRAN_CONNECTION nodes and SNOWFLAKE_TABLE nodes
        tables_per_connector: dict[str, list[str]] = {}

        for conn_row in connections:
            cid = conn_row.get("connector_id", "")
            if not cid:
                continue

            info = conn_info[cid]
            last_sync_end_str = info["last_sync_end"]
            rows_synced_raw = info["rows_synced"]
            rows_synced: int | None = None
            if rows_synced_raw and str(rows_synced_raw).strip():
                try:
                    rows_synced = int(rows_synced_raw)
                except (ValueError, TypeError):
                    rows_synced = None

            # Create FIVETRAN_CONNECTION node
            store.add_node(
                NodeType.FIVETRAN_CONNECTION.value,
                cid,
                source_id=cid,
                name=info["name"],
                status=info["status"],
                last_sync_start=last_sync_end_str if last_sync_end_str else None,
                rows_synced=rows_synced,
            )
            node_count += 1

            # Create SNOWFLAKE_TABLE nodes for each schema
            tables_per_connector[cid] = []
            schema_rows = schemas_by_connector.get(cid, [])
            for schema_row in schema_rows:
                table_schema = schema_row.get("table_schema", "")
                table_name = schema_row.get("table_name", "")
                if not table_schema or not table_name:
                    continue

                table_id = f"{cid}.{table_schema}.{table_name}"
                tables_per_connector.setdefault(cid, []).append(table_id)

                # Determine freshness from connection's last_sync_end
                try:
                    if isinstance(last_sync_end_str, str) and last_sync_end_str:
                        parse_result = self._parse_iso_timestamp(last_sync_end_str)
                        f_date = freshness_date(parse_result)
                        stale_flag = is_stale(parse_result)
                    else:
                        f_date = None
                        stale_flag = True
                except (ValueError, TypeError):
                    f_date = None
                    stale_flag = True

                store.add_node(
                    NodeType.SNOWFLAKE_TABLE.value,
                    table_id,
                    schema=table_schema,
                    name=table_name,
                    last_modified=last_sync_end_str if last_sync_end_str else None,
                    row_count=rows_synced,
                    freshness=str(f_date) if f_date else None,
                    stale=stale_flag,
                )
                node_count += 1

        # 2. Add SYNC_TO edges from FIVETRAN_CONNECTION to each SNOWFLAKE_TABLE
        for cid, table_ids in tables_per_connector.items():
            for table_id in table_ids:
                store.add_edge("SYNC_TO", cid, table_id)

        # 3. Process dbt bridge – update freshness on table nodes from bridge data
        for bridge_row in bridges:
            cid = bridge_row.get("connector_id", "")
            if not cid:
                continue
            info = conn_info.get(cid, {})
            last_sync_end_str = info.get("last_sync_end", "")

            try:
                if isinstance(last_sync_end_str, str) and last_sync_end_str:
                    parse_result = self._parse_iso_timestamp(last_sync_end_str)
                    f_date = freshness_date(parse_result)
                else:
                    continue
            except (ValueError, TypeError):
                continue

            for schema_row in schemas:
                bridge_schema = bridge_row.get("table_schema", "")
                bridge_table = bridge_row.get("table_name", "")
                if (
                    schema_row.get("table_schema") == bridge_schema
                    and schema_row.get("table_name") == bridge_table
                ):
                    table_id = f"{cid}.{bridge_schema}.{bridge_table}"
                    existing = store.node(table_id)
                    if existing and f_date:
                        existing["freshness"] = str(f_date)

        return node_count

    # ── live mode ───────────────────────────────────────────────────────

    def _ingest_live(self, store: GraphStore) -> int:
        """Query Fivetran REST API and build the graph."""
        api_token = os.environ.get("FIVETRAN_API_TOKEN")
        account = os.environ.get("FIVETRAN_ACCOUNT")

        if not api_token or not account:
            raise EnvironmentError(
                "Live mode requires FIVETRAN_API_TOKEN and FIVETRAN_ACCOUNT env vars."
            )

        base_url = f"https://api.fivetran.com/v1/connections/{account}"
        auth_string = f"{api_token}:"  # colon after token, username-only basic auth per Fivetran docs
        import base64

        encoded = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")
        request_headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

        node_count = 0

        # Fetch active connections list
        try:
            connections_data = self._fetch_json(
                base_url, request_headers, query="?status=active"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch Fivetran connections: {exc}") from exc

        connection_nodes: dict[str, dict[str, Any]] = {}

        for conn_item in connections_data.get("data", {}).get("items", []):
            connector_id = conn_item.get("id", "")
            if not connector_id:
                continue

            # Parse schema info for the connector
            try:
                schema_data = self._fetch_json(
                    base_url, request_headers, query=f"/schema/{connector_id}"
                )
            except Exception:
                schema_data = {"data": {"items": []}}

            # Extract sync metadata from connectors endpoint
            conn_detail_url = f"{base_url}/{connector_id}"
            try:
                detail_data = self._fetch_json(connector_id, request_headers)
            except Exception:
                detail_data = {}

            name = conn_item.get("service", "unknown") + "-" + connector_id[:8]
            status = conn_item.get("setup_state", "unknown")
            synced_at_str = ""
            try:
                synced_at_raw = conn_item.get("synced_at", "")
                if synced_at_raw:
                    synced_at_str = str(synced_at_raw)
            except Exception:
                pass

            rows_synced: int | None = None
            table_schemas = []
            for schema_item in schema_data.get("data", {}).get("items", []):
                ts = schema_item.get("schema_name", "")
                tn = schema_item.get("table_name", "")
                if ts and tn:
                    table_schemas.append((ts, tn))

            # Create connection node
            store.add_node(
                NodeType.FIVETRAN_CONNECTION.value,
                connector_id,
                source_id=connector_id,
                name=name,
                status=status,
                last_sync_start=synced_at_str or None,
                rows_synced=rows_synced,
            )
            node_count += 1
            connection_nodes[connector_id] = {
                "name": name,
                "status": status,
                "last_sync_end": synced_at_str,
                "table_schemas": table_schemas,
            }

        # Create SNOWFLAKE_TABLE nodes and SYNC_TO edges
        for cid, info in connection_nodes.items():
            for schema_name, table_name in info["table_schemas"]:
                table_id = f"{cid}.{schema_name}.{table_name}"
                last_sync_end_str = info.get("last_sync_end")

                if last_sync_end_str:
                    try:
                        parse_result = self._parse_iso_timestamp(last_sync_end_str)
                        f_date = freshness_date(parse_result)
                        stale_flag = is_stale(parse_result)
                    except (ValueError, TypeError):
                        f_date = None
                        stale_flag = True
                else:
                    f_date = None
                    stale_flag = True

                store.add_node(
                    NodeType.SNOWFLAKE_TABLE.value,
                    table_id,
                    schema=schema_name,
                    name=table_name,
                    last_modified=last_sync_end_str or None,
                    row_count=None,
                    freshness=str(f_date) if f_date else None,
                    stale=stale_flag,
                )
                node_count += 1

                store.add_edge("SYNC_TO", cid, table_id)

        return node_count

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _read_csv(path: pathlib.Path) -> list[dict[str, str]]:
        """Read a CSV file and return a list of row dicts."""
        if not path.exists():
            return []
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows: list[dict[str, str]] = []
            for row in reader:
                rows.append(dict(row))
            return rows

    @staticmethod
    def _parse_iso_timestamp(value: str) -> datetime.datetime:
        """Parse an ISO-8601 timestamp string into a naive datetime."""
        value = value.strip().rstrip("Z")
        # Try common formats
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
        raise ValueError(f"Unable to parse timestamp: {value!r}")

    @staticmethod
    def _fetch_json(
        base_url: str, headers: dict[str, str], query: str = ""
    ) -> dict[str, Any]:
        """Perform a GET request and return parsed JSON."""
        url = f"{base_url}{query}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
            raw = response.read()
            return json.loads(raw.decode("utf-8"))
