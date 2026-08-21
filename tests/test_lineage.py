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

"""Tests for seed_walk lineage traversal."""

from __future__ import annotations
import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from dope.cli.main import build_lineage_graph, seed_walk
from dope.core.graph import PurePyGraph


@pytest.fixture()
def sample_snapshots_path(tmp_path: Path) -> Path:
    """Create a temporary directory with full snapshot files."""
    # fivetran_connections.csv
    (tmp_path / "fivetran_connections.csv").write_text(
        "connector_id,name,status,last_sync_start,last_sync_end,rows_synced\n"
        "random_words,Random Words,active,2026-08-14T08:00:00Z,2026-08-14T08:03:12Z,4821\n"
        "stripe,Stripe Billing,active,2026-08-14T06:00:00Z,2026-08-14T06:47:05Z,12043\n",
        encoding="utf-8",
    )

    # fivetran_schemas.csv
    (tmp_path / "fivetran_schemas.csv").write_text(
        "connector_id,table_schema,table_name\n"
        "random_words,fivetran_random_words,words\n"
        "stripe,fivetran_stripe,charges\n",
        encoding="utf-8",
    )

    # fivetran_dbt_bridge.csv
    (tmp_path / "fivetran_dbt_bridge.csv").write_text(
        "connector_id,table_schema,table_name,dbt_unique_id\n"
        "random_words,fivetran_random_words,words,model.myproj.stg_random_words\n"
        "stripe,fivetran_stripe,charges,model.myproj.stg_stripe_events\n",
        encoding="utf-8",
    )

    # dbt_nodes.json with a simple lineage chain
    nodes = {
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
        "model.myproj.fct_orders": {
            "unique_id": "model.myproj.fct_orders",
            "name": "fct_orders",
            "resource_type": "model",
            "original_sql": "SELECT * FROM {{ ref('int_orders') }}",
            "config": {"materialized": "table"},
            "depends_on": {"nodes": ["model.myproj.int_orders"]},
            "tags": [],
        },
        "model.myproj.stg_random_words": {
            "unique_id": "model.myproj.stg_random_words",
            "name": "stg_random_words",
            "resource_type": "source",
            "original_sql": "",
            "config": {"materialized": "view"},
            "depends_on": {"nodes": []},
            "tags": ["fivetran"],
        },
        "model.myproj.stg_stripe_events": {
            "unique_id": "model.myproj.stg_stripe_events",
            "name": "stg_stripe_events",
            "resource_type": "source",
            "original_sql": "",
            "config": {"materialized": "view"},
            "depends_on": {"nodes": []},
            "tags": ["fivetran"],
        },
    }
    (tmp_path / "dbt_nodes.json").write_text(
        json.dumps(nodes), encoding="utf-8"
    )

    # dbt_run_results.json
    (tmp_path / "dbt_run_results.json").write_text(
        json.dumps([
            {"unique_id": "model.myproj.stg_random_words", "status": "success",
             "started_at": "2026-08-14T02:00:00Z", "finished_at": "2026-08-14T02:00:10Z",
             "execution_time": 10.12},
            {"unique_id": "model.myproj.stg_stripe_events", "status": "success",
             "started_at": "2026-08-14T02:01:30Z", "finished_at": "2026-08-14T02:01:45Z",
             "execution_time": 15.67},
            {"unique_id": "model.myproj.int_orders", "status": "success",
             "started_at": "2026-08-14T02:03:00Z", "finished_at": "2026-08-14T02:03:25Z",
             "execution_time": 25.01},
            {"unique_id": "model.myproj.fct_orders", "status": "success",
             "started_at": "2026-08-14T02:04:30Z", "finished_at": "2026-08-14T02:06:10Z",
             "execution_time": 100.55},
        ]), encoding="utf-8"
    )

    return tmp_path


class TestSeedWalk:
    """Test seed_walk returns expected structure."""

    def test_seed_walk_returns_required_keys(self, sample_snapshots_path: Path) -> None:
        g = PurePyGraph()
        result = seed_walk("random_words", g, sample_snapshots_path)

        assert "connector_id" in result
        assert "nodes" in result
        assert "edges" in result
        assert "freshness_date" in result
        assert "stale" in result
        assert result["connector_id"] == "random_words"

    def test_seed_walk_includes_dbt_nodes(self, sample_snapshots_path: Path) -> None:
        g = PurePyGraph()
        result = seed_walk("random_words", g, sample_snapshots_path)

        # Should include stg_random_words and all its downstream nodes
        assert "model.myproj.stg_random_words" in result["nodes"]

    def test_seed_walk_stripe_includes_stripe_models(self, sample_snapshots_path: Path) -> None:
        g = PurePyGraph()
        result = seed_walk("stripe", g, sample_snapshots_path)

        assert "model.myproj.stg_stripe_events" in result["nodes"]

    def test_seed_walk_unknown_connector_raises(self, sample_snapshots_path: Path) -> None:
        g = PurePyGraph()
        try:
            seed_walk("nonexistent", g, sample_snapshots_path)
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "not found" in str(e).lower()

    def test_seed_walk_with_as_of_date(self, sample_snapshots_path: Path) -> None:
        from datetime import date
        g = PurePyGraph()
        result = seed_walk("random_words", g, sample_snapshots_path, as_of=date(2026, 8, 15))

        # random_words synced Aug 14; last_biz of Aug 15 is Aug 14 → not stale
        assert result["stale"] is False
        assert result["freshness_date"] == "2026-08-14"


class TestBuildLineageGraph:
    """Test the build_lineage_graph helper function."""

    def test_build_lineage_graph_returns_tuple(self, sample_snapshots_path: Path) -> None:
        graph, results = build_lineage_graph(
            seed_connector_id="random_words",
            out_dir=sample_snapshots_path,
        )

        assert isinstance(graph, PurePyGraph)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_build_all_connectors(self, sample_snapshots_path: Path) -> None:
        graph, results = build_lineage_graph(
            use_all_connectors=True,
            out_dir=sample_snapshots_path,
        )

        connector_ids = {r.get("connector_id") for r in results if "error" not in r}
        assert "random_words" in connector_ids
        assert "stripe" in connector_ids

    def test_build_lineage_graph_missing_snapshot(self) -> None:
        with TemporaryDirectory() as td:
            try:
                build_lineage_graph(out_dir=td)
                assert False, "Expected FileNotFoundError"
            except FileNotFoundError:
                pass  # Expected
