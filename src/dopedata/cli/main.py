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

"""Command-line interface for dopedata — pipeline observability."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dopedata.core.freshness import freshness_date, is_stale, last_business_day


# ---------------------------------------------------------------------------
# Snapshot loaders
# ---------------------------------------------------------------------------

def _load_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file and return a list of row dicts."""
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load_json(path: Path) -> Any:
    """Read a JSON file and return its contents."""
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Seed walk
# ---------------------------------------------------------------------------

def seed_walk(
    connector_id: str,
    graph_store: Any,
    snapshots_dir: Path,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Walk lineage from a Fivetran connector through dbt to expose downstream.

    Parameters
    ----------
    connector_id :
        The Fivetran connector identifier (e.g. ``"stripe"``, ``"random_words"``).
    graph_store :
        A :class:`dopedata.core.graph.GraphStore` instance already populated with
        Fivetran connection, schema, bridge, and dbt node data.
    snapshots_dir :
        Path to the directory containing snapshot CSV/JSON files.
    as_of :
        Reference date for freshness computation. Defaults to today.

    Returns
    -------
    dict
        Walk result with keys ``connector_id``, ``nodes`` (list of unique_ids),
        ``edges``, ``freshness`` (dict per connector), and ``stale`` (bool).
    """
    bridge_path = snapshots_dir / "fivetran_dbt_bridge.csv"
    conns_path = snapshots_dir / "fivetran_connections.csv"

    if not conns_path.exists():
        raise FileNotFoundError(f"Fivetran connections snapshot not found: {conns_path}")
    if not bridge_path.exists():
        raise FileNotFoundError(f"Fivetran-dbt bridge snapshot not found: {bridge_path}")

    conns = _load_csv(conns_path)
    bridge_rows = _load_csv(bridge_path)

    # Find connector metadata
    conn_record: dict[str, str] | None = None
    for row in conns:
        if row.get("connector_id") == connector_id:
            conn_record = row
            break

    if conn_record is None:
        raise ValueError(f"Connector '{connector_id}' not found in snapshot.")

    # Build set of dbt model UIDs backed by this connector
    bridge_dbt_ids: list[str] = []
    for row in bridge_rows:
        if row.get("connector_id") == connector_id:
            uid = row.get("dbt_unique_id", "")
            if uid:
                bridge_dbt_ids.append(uid)

    # Load dbt nodes
    dbt_nodes_path = snapshots_dir / "dbt_nodes.json"
    dbt_nodes = _load_json(dbt_nodes_path) if dbt_nodes_path.exists() else {}

    # Collect ALL related nodes: upstream deps AND downstream consumers
    all_related_ids: set[str] = set(bridge_dbt_ids)
    all_edges: list[dict[str, str]] = []

    # Walk upstream (follow depends_on.nodes backward to find sources)
    def _collect_upstream(uid: str) -> None:
        if uid not in dbt_nodes or len(all_related_ids) > 200:
            return
        ndata = dbt_nodes[uid]
        deps = ndata.get("depends_on", {}).get("nodes", [])
        for dep in deps:
            all_edges.append({"from": dep, "to": uid})
            if dep not in all_related_ids:
                all_related_ids.add(dep)
                _collect_upstream(dep)

    # Walk downstream (find nodes that depend on any of our bridge IDs)
    def _collect_downstream(uid: str) -> None:
        if len(all_related_ids) > 200:
            return
        for other_uid, ndata in dbt_nodes.items():
            deps = ndata.get("depends_on", {}).get("nodes", [])
            if uid in deps and other_uid not in all_related_ids:
                all_related_ids.add(other_uid)
                all_edges.append({"from": uid, "to": other_uid})
                _collect_downstream(other_uid)

    # Start both traversals from bridge IDs
    for uid in bridge_dbt_ids:
        _collect_upstream(uid)
        _collect_downstream(uid)

    walk_nodes = sorted(all_related_ids)

    # Build nodes list with metadata
    nodes_with_meta: list[dict[str, Any]] = []
    for uid in walk_nodes:
        ndata = dbt_nodes.get(uid, {})
        nodes_with_meta.append({
            "unique_id": uid,
            "name": ndata.get("name", uid),
            "resource_type": ndata.get("resource_type", "unknown"),
            "materialized": ndata.get("config", {}).get("materialized", "unknown"),
        })

    # Freshness for this connector
    last_sync_end_str = conn_record.get("last_sync_end")
    freshness_date_result: date | None = None
    stale_flag = False

    if last_sync_end_str:
        last_sync_end_dt = datetime.fromisoformat(last_sync_end_str.replace("Z", "+00:00")).replace(tzinfo=None)
        stale_flag = is_stale(last_sync_end_dt, as_of=as_of)
        freshness_date_result = freshness_date(last_sync_end_dt, as_of=as_of)

    return {
        "connector_id": connector_id,
        "name": conn_record.get("name", ""),
        "nodes": walk_nodes,
        "nodes_detail": nodes_with_meta,
        "edges": all_edges,
        "freshness_date": str(freshness_date_result) if freshness_date_result else None,
        "stale": stale_flag,
        "last_sync_end": last_sync_end_str,
    }


# ---------------------------------------------------------------------------
# Freshness report
# ---------------------------------------------------------------------------

def build_freshness_report(
    snapshots_dir: Path,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Build a full freshness report for all connectors in the snapshot.

    Returns a list of dicts with keys: connector_id, name, status, last_sync_end,
    last_business_day, freshness_date, stale (bool).
    """
    conns_path = snapshots_dir / "fivetran_connections.csv"
    if not conns_path.exists():
        raise FileNotFoundError(f"Connections snapshot not found: {conns_path}")

    conn_rows = _load_csv(conns_path)
    as_of_date = as_of or date.today()
    last_biz = last_business_day(as_of_date)

    report: list[dict[str, Any]] = []
    for row in conn_rows:
        connector_id = row.get("connector_id", "")
        name = row.get("name", "")
        status = row.get("status", "")
        last_sync_end_str = row.get("last_sync_end")

        last_date: date | None = None
        if last_sync_end_str:
            ts = datetime.fromisoformat(last_sync_end_str.replace("Z", "+00:00")).replace(tzinfo=None)
            last_date = ts.date()

        stale_flag = is_stale(last_date, as_of=as_of_date)

        # Freshness date logic
        if stale_flag and last_date:
            fd = last_biz  # data is valid up to last business day
        elif last_date:
            fd = last_date
        else:
            fd = None

        report.append({
            "connector_id": connector_id,
            "name": name,
            "status": status,
            "last_sync_end": last_sync_end_str or "",
            "last_business_day": str(last_biz),
            "freshness_date": str(fd) if fd else "",
            "stale": stale_flag,
        })

    return report


# ---------------------------------------------------------------------------
# Lineage graph builder from snapshots
# ---------------------------------------------------------------------------

def build_lineage_graph(
    seed_connector_id: str | None = None,
    use_all_connectors: bool = False,
    out_dir: Path | None = None,
    as_of: date | None = None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Build a graph from snapshot files and perform seed walks.

    Parameters
    ----------
    seed_connector_id :
        Single connector to walk. If ``None`` and *use_all_connectors* is False,
        uses the first connector in the snapshot.
    use_all_connectors :
        If True, iterate over all connectors in the snapshot.
    out_dir :
        Directory for writing output files. Defaults to parent of snapshots dir.
    as_of :
        Reference date for freshness.

    Returns
    -------
    tuple
        (graph_store_instance, walk_results_list)
    """
    if out_dir is None:
        # Default: look for data/snapshots relative to cwd
        snapshots_dir = Path("data/snapshots")
    else:
        snapshots_dir = Path(out_dir)

    from dopedata.core.graph import PurePyGraph

    graph_store = PurePyGraph()

    # Load and populate graph with Fivetran + dbt snapshot data
    _populate_graph_from_snapshots(graph_store, snapshots_dir)

    # Determine which connectors to walk
    conns_path = snapshots_dir / "fivetran_connections.csv"
    conn_rows = _load_csv(conns_path) if conns_path.exists() else []

    connector_ids: list[str]
    if seed_connector_id:
        connector_ids = [seed_connector_id]
    elif use_all_connectors:
        connector_ids = [r["connector_id"] for r in conn_rows]
    else:
        connector_ids = [conn_rows[0]["connector_id"]] if conn_rows else []

    # Run seed walk for each connector
    walk_results: list[dict[str, Any]] = []
    for cid in connector_ids:
        try:
            result = seed_walk(cid, graph_store, snapshots_dir, as_of=as_of)
            walk_results.append(result)
        except (ValueError, FileNotFoundError) as exc:
            walk_results.append({
                "connector_id": cid,
                "error": str(exc),
            })

    return graph_store, walk_results


def _populate_graph_from_snapshots(graph_store: Any, snapshots_dir: Path) -> None:
    """Load all snapshot CSV/JSON files and populate the graph store."""
    conns_path = snapshots_dir / "fivetran_connections.csv"
    schemas_path = snapshots_dir / "fivetran_schemas.csv"
    bridge_path = snapshots_dir / "fivetran_dbt_bridge.csv"
    dbt_nodes_path = snapshots_dir / "dbt_nodes.json"

    if not (conns_path.exists() or dbt_nodes_path.exists()):
        raise FileNotFoundError(
            f"No snapshot files found in {snapshots_dir}. "
            f"Expected at least fivetran_connections.csv or dbt_nodes.json."
        )

    # Load Fivetran connections → graph nodes
    if conns_path.exists():
        for row in _load_csv(conns_path):
            cid = row.get("connector_id", "")
            last_end_str = row.get("last_sync_end")
            synced_at = None
            if last_end_str:
                try:
                    synced_at = datetime.fromisoformat(last_end_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            graph_store.add_node(
                "FivetranConnection",
                cid,
                source_id=cid,
                name=row.get("name", ""),
                status=row.get("status", ""),
                synced_at=synced_at.isoformat() if synced_at else None,
            )

    # Load dbt nodes → graph nodes
    if dbt_nodes_path.exists():
        dbt_nodes = _load_json(dbt_nodes_path)
        for uid, ndata in dbt_nodes.items():
            rtype = ndata.get("resource_type", "unknown")
            node_type_map = {
                "model": "dbtModel",
                "source": "dbtSource",
                "test": "dbtTest",
                "exposure": "DataProduct",
            }
            node_type = node_type_map.get(rtype, "dbtModel")
            graph_store.add_node(
                node_type,
                uid,
                name=ndata.get("name", uid),
                resource_type=rtype,
                materialized=ndata.get("config", {}).get("materialized", "unknown"),
            )

    # Load DEPENDS_ON edges from dbt nodes
    if dbt_nodes_path.exists():
        dbt_nodes = _load_json(dbt_nodes_path)
        for uid, ndata in dbt_nodes.items():
            deps = ndata.get("depends_on", {}).get("nodes", [])
            for dep in deps:
                rtype = ndata.get("resource_type", "")
                if rtype in ("model", "test"):
                    graph_store.add_edge("DEPENDS_ON", dep, uid)

    # Build additional edges from bridge + schemas for Fivetran→dbt mapping
    if conns_path.exists() and bridge_path.exists():
        bridge_rows = _load_csv(bridge_path)
        conn_rows_map: dict[str, dict] = {}
        if conns_path.exists():
            for row in _load_csv(conns_path):
                conn_rows_map[row.get("connector_id", "")] = row

        for brow in bridge_rows:
            connector_id = brow.get("connector_id", "")
            dbt_uid = brow.get("dbt_unique_id", "")
            if connector_id in conn_rows_map and dbt_uid:
                graph_store.add_edge(
                    "SYNC_TO",
                    connector_id,
                    dbt_uid,
                    table_schema=brow.get("table_schema", ""),
                    table_name=brow.get("table_name", ""),
                )


# ---------------------------------------------------------------------------
# Cypher query generation
# ---------------------------------------------------------------------------

def generate_cypher_query(view_type: str, walk_result: dict[str, Any]) -> list[dict[str, str]]:
    """Generate Cypher queries and their interpretations for a seed walk result."""
    queries: list[dict[str, str]] = []

    if view_type in ("all", "cypher"):
        cid = walk_result.get("connector_id", "")
        # Query 1: Find all downstream nodes
        q1 = {
            "description": f"Downstream lineage from connector '{cid}'",
            "query": f"MATCH (src:FivetranConnection {{id: '{cid}'}})-[:SYNC_TO*]->(n) RETURN n.id AS node_id, n.name AS name",
        }
        queries.append(q1)

        # Query 2: DEPENDS_ON chain
        nodes = walk_result.get("nodes", [])
        if nodes:
            first = nodes[0]
            q2 = {
                "description": f"Dependencies of first walked model '{first}'",
                "query": f"MATCH (a)-[:DEPENDS_ON*]->(b:dbtModel {{id: '{first}'}}) RETURN a.id AS upstream, b.id AS downstream",
            }
            queries.append(q2)

        # Query 3: Freshness check
        q3 = {
            "description": "All stale connectors",
            "query": f"MATCH (n:FivetranConnection) WHERE n.stale = true RETURN n.id, n.name, n.synced_at",
        }
        queries.append(q3)

    if view_type in ("all", "tabular"):
        # Tabular representation of walk result
        for detail in walk_result.get("nodes_detail", []):
            queries.append({
                "type": "tabular_row",
                "unique_id": detail.get("unique_id", ""),
                "name": detail.get("name", ""),
                "resource_type": detail.get("resource_type", ""),
                "materialized": detail.get("materialized", ""),
            })

    return queries


# ---------------------------------------------------------------------------
# HTML lineage visualisation
# ---------------------------------------------------------------------------

def write_lineage_html(
    walk_results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write a self-contained HTML file with lineage graph info."""
    html_parts: list[str] = []
    html_parts.append("<!DOCTYPE html>")
    html_parts.append('<html lang="en"><head><meta charset="utf-8"><title>Dope Lineage</title>')
    html_parts.append("<style>")
    html_parts.append("""
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; background: #fafafa; }
h1 { color: #1a1a2e; }
.connector-card { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
.connector-card h2 { margin-top: 0; color: #16213e; }
table { border-collapse: collapse; width: 100%; margin-top: .5rem; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: .9rem; }
th { background: #f0f0f0; }
.stale-tag { background: #ff4d4f; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: .8rem; }
.fresh-tag { background: #52c41a; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: .8rem; }
.node-type-model { color: #1890ff; }
.node-type-source { color: #13c2c2; }
.node-type-test { color: #faad14; }
.node-type-exposure { color: #722ed1; }
""")
    html_parts.append("</style></head><body>")

    total_nodes = 0
    total_edges = 0
    stale_count = 0

    for wr in walk_results:
        cid = wr.get("connector_id", "unknown")
        cname = wr.get("name", "")
        is_stale_conn = wr.get("stale", False)
        nodes_detail = wr.get("nodes_detail", [])
        stale_flag = wr.get("stale", False)
        if stale_flag:
            stale_count += 1

        html_parts.append(f'<div class="connector-card">')
        html_parts.append(f"<h2>{cname} <code>{cid}</code>"
                          f'{" <span class=\"stale-tag\">STALE</span>" if is_stale_conn else " <span class=\"fresh-tag\">FRESH</span>"}'
                          "</h2>")

        last_sync = wr.get("last_sync_end", "N/A")
        fd = wr.get("freshness_date", "N/A")
        html_parts.append(f"<p>Last sync: <code>{last_sync}</code> &nbsp;|&nbsp; Freshness date: <code>{fd}</code></p>")

        if nodes_detail:
            total_nodes += len(nodes_detail)
            total_edges += len(wr.get("edges", []))
            html_parts.append("<table><thead><tr>"
                              "<th>Node</th><th>Type</th><th>Materialized</th></tr></thead><tbody>")
            for nd in nodes_detail:
                uid = nd.get("unique_id", "")
                rtype = nd.get("resource_type", "")
                mat = nd.get("materialized", "")
                type_cls = f"node-type-{rtype}" if rtype else ""
                html_parts.append(f"<tr><td class=\"{type_cls}\"><code>{uid}</code></td>"
                                  f"<td>{rtype}</td><td>{mat}</td></tr>")
            html_parts.append("</tbody></table>")

        # Edge summary
        edges = wr.get("edges", [])
        if edges:
            html_parts.append(f"<p><strong>Edges ({len(edges)}):</strong></p><ul>")
            for edge in edges[:20]:  # cap display
                html_parts.append(f"<li><code>{edge.get('from', '')}</code> → <code>{edge.get('to', '')}</code></li>")
            if len(edges) > 20:
                html_parts.append(f"<li>… and {len(edges) - 20} more</li>")
            html_parts.append("</ul>")

        html_parts.append("</div>")

    # Summary
    summary_html = (
        f'<div class="connector-card">'
        f"<h3>Summary</h3>"
        f"<p><strong>{total_nodes}</strong> nodes, "
        f"<strong>{total_edges}</strong> edges, "
        f"<strong>{stale_count}</strong> stale connector(s).</p>"
        f"</div>"
    )
    html_parts.append(summary_html)

    # Freshness report table
    freshness_report = build_freshness_report(Path("data/snapshots"))
    if freshness_report:
        html_parts.append('<h3>All Connectors – Freshness Report</h3><table><thead><tr>'
                          "<th>Connector</th><th>Last Sync End</th>"
                          "<th>Last Business Day</th><th>Freshness Date</th><th>Status</th></tr></thead><tbody>")
        for fr in freshness_report:
            status = "STALE" if fr["stale"] else "FRESH"
            tag_class = "stale-tag" if fr["stale"] else "fresh-tag"
            html_parts.append(f"<tr>"
                              f"<td><code>{fr['connector_id']}</code> — {fr['name']}</td>"
                              f"<td>{fr['last_sync_end']}</td>"
                              f"<td>{fr['last_business_day']}</td>"
                              f"<td>{fr['freshness_date']}</td>"
                              f"<td><span class=\"{tag_class}\">{status}</span></td>"
                              f"</tr>")
        html_parts.append("</tbody></table>")

    html_parts.append("</body></html>")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(html_parts))


# ---------------------------------------------------------------------------
# Freshness CSV report writer
# ---------------------------------------------------------------------------

def write_freshness_csv(report: list[dict[str, Any]], output_path: Path) -> None:
    """Write the freshness report to a CSV file."""
    if not report:
        return
    fieldnames = list(report[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="dopedata",
        description="Pipeline observability — Fivetran + dbt lineage, freshness, static viz",
    )
    parser.add_argument(
        "--seed",
        type=str,
        default=None,
        help="Single Fivetran connector ID to walk (default: from env DOPE_SEED or first in snapshot)",
    )
    parser.add_argument(
        "--all-connectors",
        action="store_true",
        default=False,
        help="Walk every connector in the snapshot instead of a single seed",
    )
    parser.add_argument(
        "--backend",
        choices=["pure", "kuzu"],
        default="pure",
        help="Graph backend: 'pure' (zero-dep) or 'kuzu' (requires kuzu package)",
    )
    parser.add_argument(
        "--view",
        choices=["all", "cypher", "tabular", "html"],
        default="all",
        help="Output view mode (default: all)",
    )
    parser.add_argument(
        "--mode",
        choices=["snapshot", "live"],
        default="snapshot",
        help="Data source mode (default: snapshot)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory for generated files (default: data/snapshots/)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help='Override "today" date for freshness computation (YYYY-MM-DD)',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve out_dir
    snapshots_dir = Path(args.out_dir or "data/snapshots")
    if not snapshots_dir.exists():
        print(f"Error: snapshot directory not found: {snapshots_dir}", file=sys.stderr)
        return 1

    # Resolve as_of date
    as_of_date: date | None = None
    if args.as_of:
        try:
            as_of_date = date.fromisoformat(args.as_of)
        except ValueError:
            print(f"Error: invalid --as-of date '{args.as_of}' (expected YYYY-MM-DD)", file=sys.stderr)
            return 1

    # Determine seed
    seed_id = args.seed
    if not seed_id:
        env_seed = os.environ.get("DOPE_SEED")
        if env_seed:
            seed_id = env_seed

    print("=" * 72)
    print("Dopedata — Pipeline Observability")
    print(f"  mode         : {args.mode}")
    print(f"  backend      : {args.backend}")
    print(f"  view         : {args.view}")
    print(f"  snapshots_dir: {snapshots_dir}")
    if args.as_of:
        print(f"  as-of date   : {as_of_date}")
    print("=" * 72)

    # Build the graph and perform seed walks
    try:
        graph_store, walk_results = build_lineage_graph(
            seed_connector_id=seed_id,
            use_all_connectors=args.all_connectors,
            out_dir=snapshots_dir,
            as_of=as_of_date,
        )
    except Exception as exc:
        print(f"Error building lineage graph: {exc}", file=sys.stderr)
        return 1

    # Print output based on view mode
    if args.view in ("all", "cypher"):
        for wr in walk_results:
            if "error" in wr:
                print(f"\n[ERROR] Connector '{wr.get('connector_id', '?')}': {wr['error']}")
                continue
            queries = generate_cypher_query(args.view, wr)
            for q in queries:
                desc = q.get("description", "")
                query_str = q.get("query", "")
                if not desc or not query_str:
                    continue
                print(f"\n-- {desc}")
                print(query_str)

    if args.view in ("all", "tabular"):
        for wr in walk_results:
            if "error" in wr:
                continue
            nodes_detail = wr.get("nodes_detail", [])
            if not nodes_detail:
                continue
            stale_tag = " [STALE]" if wr.get("stale") else ""
            print(f"\n--- Connector: {wr.get('name', '')} ({wr['connector_id']}){stale_tag}")
            print(f"  {'Node':<60} {'Type':<14} {'Materialized':<12}")
            print(f"  {'-'*60} {'-'*14} {'-'*12}")
            for nd in nodes_detail:
                print(f"  {nd['unique_id']:<60} {nd['resource_type']:<14} {nd['materialized']:<12}")

    # Write HTML output
    if args.view in ("all", "html"):
        html_path = snapshots_dir / f"lineage_graph_{seed_id or 'all'}.html"
        write_lineage_html(walk_results, html_path)
        print(f"\n[OK] Lineage HTML written to: {html_path}")

    # Write freshness CSV report
    try:
        freshness_report = build_freshness_report(snapshots_dir, as_of=as_of_date)
        freshness_csv_path = snapshots_dir / "freshness_report.csv"
        write_freshness_csv(freshness_report, freshness_csv_path)
        print(f"[OK] Freshness CSV written to: {freshness_csv_path}")
    except Exception as exc:
        print(f"[WARN] Could not write freshness CSV: {exc}", file=sys.stderr)

    # Summary
    total_nodes = sum(len(wr.get("nodes", [])) for wr in walk_results if "error" not in wr)
    total_edges = sum(len(wr.get("edges", [])) for wr in walk_results if "error" not in wr)
    stale_count = sum(1 for wr in walk_results if wr.get("stale"))
    print(f"\n{'='*72}")
    print(f"{total_nodes} nodes, {total_edges} edges, {stale_count} stale.")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
