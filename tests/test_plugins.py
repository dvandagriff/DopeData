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

"""Tests for FivetranPlugin and DbtPlugin snapshot ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from dope.core.graph import PurePyGraph
from dope.plugins import DbtPlugin, FivetranPlugin


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def sample_snapshots(tmp_path: Path) -> Path:
    """Create a temporary directory with minimal snapshot files for testing."""
    # fivetran_connections.csv
    conns_csv = tmp_path / "fivetran_connections.csv"
    conns_csv.write_text(
        "connector_id,name,status,last_sync_start,last_sync_end,rows_synced\n"
        "stripe,Stripe Billing,active,2026-08-14T06:00:00Z,2026-08-14T06:47:05Z,12043\n",
        encoding="utf-8",
    )

    # fivetran_schemas.csv
    schemas_csv = tmp_path / "fivetran_schemas.csv"
    schemas_csv.write_text(
        "connector_id,table_schema,table_name\n"
        "stripe,fivetran_stripe,charges\n"
        "stripe,fivetran_stripe,invoices\n",
        encoding="utf-8",
    )

    # fivetran_dbt_bridge.csv
    bridge_csv = tmp_path / "fivetran_dbt_bridge.csv"
    bridge_csv.write_text(
        "connector_id,table_schema,table_name,dbt_unique_id\n"
        "stripe,fivetran_stripe,charges,model.myproj.stg_stripe_events\n",
        encoding="utf-8",
    )

    # dbt_nodes.json (minimal — just one model with a dependency)
    nodes_json = tmp_path / "dbt_nodes.json"
    nodes_json.write_text(
        json.dumps({
            "model.myproj.stg_orders": {
                "unique_id": "model.myproj.stg_orders",
                "name": "stg_orders",
                "resource_type": "source",
                "original_sql": "",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": []},
                "tags": [],
            },
            "model.myproj.int_orders": {
                "unique_id": "model.myproj.int_orders",
                "name": "int_orders",
                "resource_type": "model",
                "original_sql": "SELECT * FROM {{ ref('stg_orders') }}",
                "config": {"materialized": "view"},
                "depends_on": {"nodes": ["model.myproj.stg_orders"]},
                "tags": [],
            },
        }),
        encoding="utf-8",
    )

    # dbt_run_results.json
    run_results_json = tmp_path / "dbt_run_results.json"
    run_results_json.write_text(
        json.dumps([
            {
                "unique_id": "model.myproj.stg_orders",
                "status": "success",
                "started_at": "2026-08-14T02:00:00Z",
                "finished_at": "2026-08-14T02:00:15Z",
                "execution_time": 15.23,
            },
            {
                "unique_id": "model.myproj.int_orders",
                "status": "success",
                "started_at": "2026-08-14T02:03:00Z",
                "finished_at": "2026-08-14T02:03:25Z",
                "execution_time": 25.01,
            },
        ]),
        encoding="utf-8",
    )

    return tmp_path


# ── FivetranPlugin tests ───────────────────────────────────────────────


class TestFivetranPlugin:
    """Test FivetranPlugin snapshot ingestion."""

    def test_ingest_creates_fivetran_nodes(self, sample_snapshots: Path) -> None:
        plugin = FivetranPlugin(sample_snapshots)
        store = PurePyGraph()
        total = plugin.ingest(store, mode="snapshot")

        # Should have created at least the stripe connector node
        stripe = store.node("stripe")
        assert stripe is not None
        assert stripe["name"] == "Stripe Billing"
        assert stripe["status"] == "active"

    def test_ingest_creates_snowflake_table_nodes(self, sample_snapshots: Path) -> None:
        plugin = FivetranPlugin(sample_snapshots)
        store = PurePyGraph()
        plugin.ingest(store, mode="snapshot")

        table1 = store.node("stripe.fivetran_stripe.charges")
        assert table1 is not None
        assert table1["schema"] == "fivetran_stripe"
        assert table1["name"] == "charges"

    def test_ingest_creates_sync_edges(self, sample_snapshots: Path) -> None:
        plugin = FivetranPlugin(sample_snapshots)
        store = PurePyGraph()
        plugin.ingest(store, mode="snapshot")

        # Check SYNC_TO edges exist (at least one for the single test schema)
        out_edges = [e for e in store._edges if e["rel_type"] == "SYNC_TO"]
        assert len(out_edges) >= 1


class TestDbtPlugin:
    """Test DbtPlugin snapshot ingestion."""

    def test_ingest_creates_model_nodes(self, sample_snapshots: Path) -> None:
        plugin = DbtPlugin(sample_snapshots)
        store = PurePyGraph()
        total = plugin.ingest(
            store, mode="snapshot", node_types=["model", "source"]
        )

        stg = store.node("model.myproj.stg_orders")
        assert stg is not None
        assert stg["type"] == "dbtSource"  # source → dbtSource

        int_model = store.node("model.myproj.int_orders")
        assert int_model is not None
        assert int_model["type"] == "dbtModel"

    def test_ingest_creates_depends_on_edges(self, sample_snapshots: Path) -> None:
        plugin = DbtPlugin(sample_snapshots)
        store = PurePyGraph()
        plugin.ingest(
            store, mode="snapshot", node_types=["model", "source"]
        )

        deps = [e for e in store._edges if e["rel_type"] == "DEPENDS_ON"]
        assert len(deps) >= 1
        # int_orders DEPENDS_ON stg_orders (downstream → upstream)
        dep = next((e for e in deps if e["from_id"] == "model.myproj.int_orders"), None)
        assert dep is not None
        assert dep["to_id"] == "model.myproj.stg_orders"

    def test_ingest_with_run_results(self, sample_snapshots: Path) -> None:
        plugin = DbtPlugin(sample_snapshots)
        store = PurePyGraph()
        plugin.ingest(
            store, mode="snapshot", node_types=["model"]
        )

        model = store.node("model.myproj.int_orders")
        assert model is not None
        assert model.get("run_status") == "success"

    def test_ingest_filters_by_node_type(self, sample_snapshots: Path) -> None:
        plugin = DbtPlugin(sample_snapshots)
        store = PurePyGraph()
        # Only ingest models (not sources)
        total = plugin.ingest(store, mode="snapshot", node_types=["model"])

        # stg_orders is a "source" type → should NOT be in the graph
        assert store.node("model.myproj.stg_orders") is None
        # int_orders is a "model" type → should be in the graph
        assert store.node("model.myproj.int_orders") is not None

    def test_ingest_empty_snapshots_dir(self) -> None:
        with TemporaryDirectory() as td:
            plugin = DbtPlugin(Path(td))
            store = PurePyGraph()
            total = plugin.ingest(store, mode="snapshot")
            assert total == 0
