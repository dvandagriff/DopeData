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

"""Freshness report – tabular view of pipeline staleness."""

from __future__ import annotations

import csv
import datetime
import logging
import os
import pathlib
from typing import TYPE_CHECKING, Any

from dopedata.core.freshness import freshness_date, is_stale

if TYPE_CHECKING:
    from dopedata.core.graph import GraphStore

logger = logging.getLogger(__name__)


def stale_report(
    store: GraphStore,
    as_of: datetime.date | None = None,
) -> str:
    """Return a formatted text table of all nodes' freshness status.

    The report is grouped by node type and exported to CSV at
    ``data/snapshots/freshness_report.csv``.

    Parameters
    ----------
    store :
        A :class:`GraphStore` implementation.
    as_of :
        Reference date for staleness calculation. Defaults to today.

    Returns
    -------
    str
        The formatted text table (also written to CSV).
    """
    # Collect all nodes by iterating through the store
    all_nodes: list[dict[str, Any]] = _get_all_nodes(store)

    if not all_nodes:
        report = "No nodes found in the graph.\n"
        return report

    stale_count = 0
    rows: list[dict[str, Any]] = []

    for node in all_nodes:
        node_id = node.get("id", "unknown")
        node_type = node.get("type", "unknown")
        freshness_val = node.get("freshness")
        stale_flag = node.get("stale")

        # Compute staleness if not already set
        if stale_flag is None and freshness_val is None:
            last_run = _extract_last_run_end(node)
            if last_run is not None:
                try:
                    f_date = freshness_date(last_run, as_of=as_of)
                    stale_flag = is_stale(last_run, as_of=as_of)
                    freshness_val = str(f_date)
                except (ValueError, TypeError):
                    stale_flag = True

        if stale_flag or stale_flag is None:
            stale_count += 1

        rows.append({
            "id": node_id,
            "type": node_type,
            "freshness": freshness_val or "",
            "stale": "true" if stale_flag else "false",
            "name": node.get("name", ""),
            "row_count": node.get("row_count") or "",
        })

    # Sort by type then id for consistent output
    rows.sort(key=lambda r: (r["type"], r["id"]))

    # Format the text table
    report = _format_table(rows)

    # Export to CSV
    _write_csv_report(rows)

    return report


# ── internal helpers ───────────────────────────────────────────────────

def _get_all_nodes(store: GraphStore) -> list[dict[str, Any]]:
    """Retrieve all nodes from the store.

    Attempts a Cypher query first; falls back to iterating _nodes directly
    for PurePyGraph backends.
    """
    # Try Cypher-based retrieval
    try:
        results = store.query("MATCH (n) RETURN n")
        nodes: list[dict[str, Any]] = []
        for row in results:
            node_data = row.get("n")
            if isinstance(node_data, dict):
                nodes.append(node_data)
        if nodes:
            return nodes
    except Exception:  # noqa: BLE001
        pass

    # Fallback: access _nodes directly (PurePyGraph internal attribute)
    if hasattr(store, "_nodes") and isinstance(store._nodes, dict):
        return list(store._nodes.values())

    logger.warning("Unable to retrieve nodes from store.")
    return []


def _extract_last_run_end(node: dict[str, Any]) -> datetime.date | datetime.datetime | None:
    """Best-effort extraction of a last-run timestamp from node properties."""
    # Try various common key names for the last run end time
    for key in ("last_modified", "end_time", "last_sync_end", "finished_at",
                 "loaded_at"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            try:
                return _parse_iso_date(val)
            except (ValueError, TypeError):
                continue
    return None


def _parse_iso_date(value: str) -> datetime.date | datetime.datetime:
    """Parse a date/datetime string."""
    value = value.strip().rstrip("Z")
    # Try datetime first
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
    # Try date only
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date: {value!r}")


def _format_table(rows: list[dict[str, Any]]) -> str:
    """Format rows as a fixed-width text table."""
    if not rows:
        return ""

    # Column definitions: (header, key)
    columns = [
        ("NODE_ID", "id"),
        ("TYPE", "type"),
        ("LAST_RUN_END", "freshness"),
        ("FRESHNESS", "freshness"),
        ("STALE", "stale"),
        ("ROWS", "row_count"),
    ]

    # Compute column widths
    col_widths: dict[str, int] = {}
    for header, _key in columns:
        col_widths[header] = len(header)

    for row in rows:
        for header, key in columns:
            val = row.get(key, "")
            str_val = f"[STALE] {val}" if header == "STALE" and row.get("stale") == "true" else val
            col_widths[header] = max(col_widths[header], len(str(str_val)))

    # Build format string
    header_parts = [h.ljust(w) for h, w in zip(col_widths.keys(), col_widths.values())]
    header_line = " | ".join(header_parts)
    separator = "-+-".join("-" * w for w in col_widths.values())

    lines: list[str] = [header_line, separator]

    stale_total = 0
    total_count = len(rows)

    for row in rows:
        parts = []
        is_any_stale = False
        for header, key in columns:
            val = row.get(key, "")
            if header == "STALE" and row.get("stale") == "true":
                val = f"[STALE] {val}"
                is_any_stale = True
            elif header == "TYPE":
                pass  # keep original type
            elif header == "FRESHNESS":
                # If stale, note it
                if row.get("stale") == "true" and val:
                    val = f"{val} (stale)"
                elif not val:
                    val = ""
            parts.append(str(val).ljust(col_widths[header]))

        lines.append(" | ".join(parts))
        if is_any_stale:
            stale_total += 1

    # Summary footer
    lines.append("")
    lines.append(f"Total nodes: {total_count}, Stale nodes: {stale_total}")

    return "\n".join(lines)


def _write_csv_report(rows: list[dict[str, Any]]) -> None:
    """Write the report rows to a CSV file."""
    snap_dir = _resolve_snapshots_dir()
    csv_path = snap_dir / "freshness_report.csv"

    # Ensure parent directory exists
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["id", "type", "freshness", "stale", "name", "row_count"]

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _resolve_snapshots_dir() -> pathlib.Path:
    """Return the snapshot directory path."""
    env_val = os.environ.get("DOPE_SNAPSHOT_DIR")
    if env_val:
        return pathlib.Path(env_val)
    candidate = pathlib.Path(__file__).resolve().parents[2] / "data" / "snapshots"
    if candidate.exists():
        return candidate
    return pathlib.Path.cwd() / "data" / "snapshots"
