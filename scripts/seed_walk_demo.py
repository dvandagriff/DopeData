#!/usr/bin/env python3
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

"""Phase 2 demo: seed walk loop over all connector IDs.

Demonstrates the 4-line core loop:

    graph = PurePyGraph()
    [load plugins into graph]
    connector_ids = load_snapshot(...)
    [ result = plugin._build_seed_walk(cid) for cid in connector_ids ]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dope.cli.main import seed_walk  # noqa: E402
from dope.core.graph import PurePyGraph  # noqa: E402
from dope.plugins import DbtPlugin, FivetranPlugin  # noqa: E402


def _load_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file and return a list of row dicts."""
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    snapshots_dir = Path("data/snapshots")

    print("=" * 70)
    print("Dope Seed Walk Demo — All Connectors (4-line loop)")
    print("=" * 70)

    # Load connector IDs from snapshot
    conns_path = snapshots_dir / "fivetran_connections.csv"
    conn_rows = _load_csv(conns_path) if conns_path.exists() else []
    connector_ids = [row["connector_id"] for row in conn_rows]

    print(f"\nSnapshot: {snapshots_dir}")
    print(f"Connectors found: {', '.join(connector_ids)}")
    print()

    # The 4-line loop:
    #   graph = PurePyGraph()
    #   [populate with plugins]
    #   connector_ids = [...]
    #   [seed_walk for each cid]
    graph = PurePyGraph()

    fivetran_plugin = FivetranPlugin(snapshots_dir)
    dbt_plugin = DbtPlugin(snapshots_dir)

    fivetran_plugin.ingest(graph, mode="snapshot")
    dbt_plugin.ingest(
        graph, mode="snapshot", node_types=["model", "test", "exposure", "source"]
    )

    print("-" * 70)
    for cid in connector_ids:
        print(f"\nWalking connector: {cid}")
        try:
            result = seed_walk(cid, graph, snapshots_dir)
            stale_tag = " [STALE]" if result.get("stale") else ""
            print(f"  Name       : {result.get('name', '')}{stale_tag}")
            print(f"  Nodes      : {len(result.get('nodes', []))} downstream models")
            print(f"  Edges      : {len(result.get('edges', []))}")
            print(f"  Freshness  : {result.get('freshness_date', 'N/A')}")
            print(f"  Stale      : {result.get('stale', False)}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    # Summary
    walk_results = [
        seed_walk(c, graph, snapshots_dir)
        for c in connector_ids
    ]
    total_nodes = sum(len(r.get("nodes", [])) for r in walk_results if "error" not in r)
    print("\n" + "=" * 70)
    print(f"Done. {len(connector_ids)} connectors walked, {total_nodes} lineage nodes.")
    print("=" * 70)


if __name__ == "__main__":
    main()
