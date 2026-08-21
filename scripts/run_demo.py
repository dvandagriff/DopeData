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

"""One-shot demo: load snapshots, run seed walks, print reports."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so we can import dope as a package.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dope.cli.main import (  # noqa: E402
    build_freshness_report,
    generate_cypher_query,
    seed_walk,
    write_freshness_csv,
    write_lineage_html,
)
from dope.core.graph import PurePyGraph  # noqa: E402
from dope.plugins import DbtPlugin, FivetranPlugin  # noqa: E402


def main() -> None:
    snapshots_dir = Path("data/snapshots")

    if not snapshots_dir.exists():
        print(f"Error: snapshot directory not found: {snapshots_dir}", file=sys.stderr)
        sys.exit(1)

    graph_store = PurePyGraph()

    # Load both plugins in snapshot mode
    fivetran_plugin = FivetranPlugin(snapshots_dir)
    dbt_plugin = DbtPlugin(snapshots_dir)

    print("Loading Fivetran snapshot...")
    n1 = fivetran_plugin.ingest(graph_store, mode="snapshot")
    print(f"  -> {n1} entities ingested (Fivetran)")

    print("Loading dbt manifest & run results...")
    n2 = dbt_plugin.ingest(
        graph_store,
        mode="snapshot",
        node_types=["model", "test", "exposure", "source"],
    )
    print(f"  -> {n2} entities ingested (dbt)")

    print()

    # Run seed walk for 'random_words' and 'stripe'
    connectors_to_walk = ["random_words", "stripe"]
    all_walk_results: list = []

    for cid in connectors_to_walk:
        print("-" * 60)
        print(f"Seed walk: {cid}")
        print("-" * 60)

        result = seed_walk(cid, graph_store, snapshots_dir)
        all_walk_results.append(result)

        # Print Cypher queries + results
        queries = generate_cypher_query("cypher", result)
        for q in queries:
            desc = q.get("description", "")
            query_str = q.get("query", "")
            if desc and query_str:
                print(f"\n-- {desc}")
                print(query_str)

        # Print tabular freshness report
        stale_tag = " [STALE]" if result.get("stale") else ""
        print(f"\n--- Connector: {result.get('name', '')} ({cid}){stale_tag}")
        print(f"  {'Node':<70} {'Type':<14} {'Materialized':<12}")
        print(f"  {'-'*70} {'-'*14} {'-'*12}")
        for nd in result.get("nodes_detail", []):
            print(
                f"  {nd['unique_id']:<70} "
                f"{nd['resource_type']:<14} "
                f"{nd['materialized']:<12}"
            )

    print()

    # Write lineage_graph.html and print its path
    html_path = snapshots_dir / "lineage_graph_demo.html"
    write_lineage_html(all_walk_results, html_path)
    print(f"[OK] Lineage HTML written to: {html_path}")

    # Write freshness_report.csv
    freshness_report = build_freshness_report(snapshots_dir)
    freshness_csv_path = snapshots_dir / "freshness_report.csv"
    write_freshness_csv(freshness_report, freshness_csv_path)
    print(f"[OK] Freshness CSV written to: {freshness_csv_path}")

    # Print 3-line summary
    total_nodes = sum(
        len(wr.get("nodes", [])) for wr in all_walk_results if "error" not in wr
    )
    total_edges = sum(
        len(wr.get("edges", [])) for wr in all_walk_results if "error" not in wr
    )
    stale_count = sum(1 for wr in all_walk_results if wr.get("stale"))
    print(f"{total_nodes} nodes, {total_edges} edges, {stale_count} stale.")


if __name__ == "__main__":
    main()
