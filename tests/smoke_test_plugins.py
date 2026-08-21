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

"""Smoke test for plugins + query layer."""

from __future__ import annotations

import csv
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from dope.core.graph import PurePyGraph
from dope.plugins.fivetran import FivetranPlugin
from dope.plugins.dbt import DbtPlugin
from dope.query.lineage import seed_walk
from dope.query.freshness_report import stale_report
from dope.query.viz import generate_html


def _setup_test_data(snapshot_dir: pathlib.Path) -> None:
    """Create minimal test CSV/JSON files."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # fivetran_connections.csv
    conns_path = snapshot_dir / "fivetran_connections.csv"
    with open(conns_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "connector_id", "name", "status", "last_sync_start", "last_sync_end", "rows_synced"
        ])
        writer.writeheader()
        writer.writerow({
            "connector_id": "conn_001", "name": "stripe_payments", "status": "connected",
            "last_sync_start": "2026-08-19T00:00:00Z", "last_sync_end": "2026-08-19T04:30:00Z",
            "rows_synced": "150000"
        })
        writer.writerow({
            "connector_id": "conn_002", "name": "salesforce_contacts", "status": "connected",
            "last_sync_start": "2026-08-18T00:00:00Z", "last_sync_end": "2026-08-15T03:00:00Z",
            "rows_synced": "50000"
        })

    # fivetran_schemas.csv
    schemas_path = snapshot_dir / "fivetran_schemas.csv"
    with open(schemas_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "connector_id", "table_schema", "table_name"
        ])
        writer.writeheader()
        for cid in ("conn_001", "conn_002"):
            writer.writerow({"connector_id": cid, "table_schema": "public", "table_name": f"table_{cid}"})

    # fivetran_dbt_bridge.csv
    bridge_path = snapshot_dir / "fivetran_dbt_bridge.csv"
    with open(bridge_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "connector_id", "table_schema", "table_name", "dbt_unique_id"
        ])
        writer.writeheader()
        for cid in ("conn_001", "conn_002"):
            writer.writerow({"connector_id": cid, "table_schema": "public", "table_name": f"table_{cid}", "dbt_unique_id": f"fivetran.{cid}.public.table_{cid}"})

    # dbt_nodes.json — list of node dicts (standard format)
    nodes_path = snapshot_dir / "dbt_nodes.json"
    with open(nodes_path, "w", encoding="utf-8") as fh:
        json.dump({
            "nodes": [
                {
                    "unique_id": "model.my_project.orders",
                    "name": "orders",
                    "resource_type": "model",
                    "package_name": "my_project",
                    "config": {"materialized": "table"},
                    "depends_on": {"nodes": ["conn_001.public.table_conn_001"]}
                },
                {
                    "unique_id": "test.my_project.orders_not_null.id",
                    "name": "not_null_id",
                    "resource_type": "test",
                    "package_name": "my_project",
                    "depends_on": {"nodes": ["model.my_project.orders"]},
                    "test_metadata": {"type": "not_null"}
                },
                {
                    "unique_id": "source.my_project.public.table_conn_001",
                    "name": "table_conn_001",
                    "resource_type": "source",
                    "package_name": "my_project"
                },
                {
                    "unique_id": "exposure.my_project.dashboard",
                    "name": "sales_dashboard",
                    "resource_type": "exposure",
                    "type": "dashboard",
                    "owner": {"name": "Alice"},
                    "depends_on": {"nodes": ["model.my_project.orders"]}
                }
            ]
        }, fh)

    # dbt_run_results.json
    results_path = snapshot_dir / "dbt_run_results.json"
    with open(results_path, "w", encoding="utf-8") as fh:
        json.dump([
            {
                "unique_id": "model.my_project.orders",
                "status": "success",
                "started_at": "2026-08-19T05:00:00Z",
                "finished_at": "2026-08-19T05:05:00Z",
                "execution_time": 300.5
            },
            {
                "unique_id": "test.my_project.orders_not_null.id",
                "status": "pass",
                "started_at": "2026-08-19T05:06:00Z",
                "finished_at": "2026-08-19T05:06:01Z",
                "execution_time": 1.2
            }
        ], fh)


def main() -> None:
    """Run the full smoke test."""
    # Setup test data in a temp dir under the project
    tmp_dir = pathlib.Path(__file__).resolve().parent / ".tmp_smoke_test"
    snap_dir = tmp_dir / "snapshots"
    _setup_test_data(snap_dir)

    # ---- Test FivetranPlugin ----
    print("=== Testing FivetranPlugin ===")
    graph = PurePyGraph()
    fivetran = FivetranPlugin()
    node_count = fivetran.ingest(graph, mode="snapshot", snapshot_dir=snap_dir)
    assert node_count > 0, "Fivetran plugin should have created nodes"
    print(f"  Created {node_count} nodes")

    # Verify key nodes exist
    c1 = graph.node("conn_001")
    assert c1 is not None, "Connector node conn_001 should exist"
    assert c1["type"] == "FivetranConnection", f"Type mismatch: {c1['type']}"

    # Verify edges exist
    neighbors = graph.neighbors("conn_001")
    assert len(neighbors) > 0, "conn_001 should have SYNC_TO edges"
    print(f"  Connector conn_001 has {len(neighbors)} synced tables")

    # ---- Test DbtPlugin ----
    print("\n=== Testing DbtPlugin ===")
    graph2 = PurePyGraph()
    dbt = DbtPlugin()
    node_count2 = dbt.ingest(graph2, mode="snapshot", snapshot_dir=snap_dir)
    assert node_count2 > 0, "Dbt plugin should have created nodes"
    print(f"  Created {node_count2} nodes")

    model = graph2.node("model.my_project.orders")
    assert model is not None, "Model node should exist"
    print(f"  Model 'orders' materialization: {model.get('materialization')}")

    test_node = graph2.node("test.my_project.orders_not_null.id")
    assert test_node is not None, "Test node should exist"
    print(f"  Test 'not_null_id' status: {test_node.get('status')}")

    # ---- Test seed_walk (combined graph) ----
    print("\n=== Testing seed_walk ===")
    combined = PurePyGraph()
    fivetran.ingest(combined, mode="snapshot", snapshot_dir=snap_dir)
    dbt.ingest(combined, mode="snapshot", snapshot_dir=snap_dir)

    result = seed_walk(combined, "conn_001", depth_up=2, depth_down=2)
    assert "nodes" in result, "Result should have 'nodes'"
    assert "edges" in result, "Result should have 'edges'"
    assert "stale_count" in result, "Result should have 'stale_count'"
    print(f"  Walk found {len(result['nodes'])} nodes, {len(result['edges'])} edges, {result['stale_count']} stale")

    # ---- Test stale_report ----
    print("\n=== Testing stale_report ===")
    report = stale_report(combined)
    assert "NODE_ID" in report, "Report should contain header"
    lines = [l for l in report.splitlines() if l.strip()]
    assert len(lines) > 2, "Report should have more than just a header"
    print(f"  Report has {len(lines)} lines")

    # ---- Test generate_html ----
    print("\n=== Testing generate_html ===")
    output = generate_html(seed_walk_result=result)
    assert pathlib.Path(output).exists(), f"HTML file should exist at {output}"
    size = pathlib.Path(output).stat().st_size
    assert size < 200_000, f"HTML file should be < 200KB, got {size}"
    print(f"  Generated HTML at {output} ({size} bytes)")

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n=== All smoke tests passed! ===")


if __name__ == "__main__":
    main()
