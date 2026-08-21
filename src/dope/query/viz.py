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

"""Generate a self-contained HTML file with a Cytoscape.js graph visualization."""

from __future__ import annotations

import datetime
import json
import logging
import pathlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── colour constants ──────────────────────────────────────────────────

_COLOR_GREEN = "#22c55e"   # fresh
_COLOR_RED = "#ef4444"     # stale
_COLOR_GREY = "#9ca3af"    # no run data / unknown


def generate_html(
    seed_walk_result: dict[str, Any] | None = None,
    output_path: str | None = None,
) -> str:
    """Generate a self-contained HTML file with Cytoscape.js visualization.

    Parameters
    ----------
    seed_walk_result :
        Dict with ``nodes`` and ``edges`` keys, as returned by
        :func:`~dope.query.lineage.seed_walk`. If *None*, produces an
        empty graph placeholder.
    output_path :
        Where to write the HTML file. Defaults to
        ``data/snapshots/lineage.html``.

    Returns
    -------
    str
        The filesystem path of the generated HTML file.
    """
    if output_path is None:
        snap_dir = pathlib.Path("data/snapshots")
        snap_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(snap_dir / "lineage.html")

    nodes_data: list[dict[str, Any]] = []
    edges_data: list[dict[str, Any]] = []

    if seed_walk_result:
        raw_nodes = seed_walk_result.get("nodes", [])
        raw_edges = seed_walk_result.get("edges", [])

        for node in raw_nodes:
            nodes_data.append(_normalize_node(node))

        for edge in raw_edges:
            edges_data.append({
                "data": {
                    "id": _edge_id(edge),
                    "source": edge.get("from_id", ""),
                    "target": edge.get("to_id", ""),
                    "type": edge.get("rel_type", ""),
                }
            })

    total_nodes = len(nodes_data)

    elements = {
        "nodes": [
            {
                "data": {
                    **nd,
                    "id": str(nd.get("id", "")),
                    "label": nd.get("name", nd.get("id", "unknown")),
                }
            }
            for nd in nodes_data
        ],
        "edges": edges_data,
    }

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    html_content = _build_template(
        elements_json=json.dumps(elements),
        timestamp=timestamp,
        total_nodes=total_nodes,
    )

    out_path = pathlib.Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html_content)

    return str(out_path)


# ── helpers ───────────────────────────────────────────────────────────

def _normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw node dict into the format expected by the HTML template."""
    node_type = node.get("type", "unknown")
    stale_flag = node.get("stale")

    # Determine fill colour
    if stale_flag is True:
        fill_color = _COLOR_RED
    elif stale_flag is False:
        fill_color = _COLOR_GREEN
    else:
        fill_color = _COLOR_GREY

    # Font size by node category (models are most important → biggest)
    size_priority: dict[str, int] = {
        "FivetranConnection": 38,
        "SnowflakeTable": 28,
        "dbtModel": 42,
        "dbtTest": 18,
        "dbtSource": 22,
        "DataProduct": 30,
    }
    node_size = size_priority.get(node_type, 24)

    # Short type name for display / CSS selector
    short_type = _short_type_name(node_type)

    return {
        "id": str(node.get("id", "")),
        "type": short_type,
        "name": node.get("name", node.get("id", "unknown")),
        "node_type": node_type,
        "stale": stale_flag,
        "fill_color": fill_color,
        "font_size": str(node_size),
    }


def _short_type_name(canonical: str) -> str:
    """Return a short label for CSS selector matching."""
    mapping = {
        "FivetranConnection": "Connection",
        "SnowflakeTable": "Table",
        "dbtModel": "Model",
        "dbtTest": "Test",
        "dbtSource": "Source",
        "DataProduct": "Product",
    }
    return mapping.get(canonical, canonical.split(".")[-1] if "." in canonical else canonical[:20])


def _edge_id(edge: dict[str, Any]) -> str:
    """Generate a unique edge identifier."""
    rt = edge.get("rel_type", "unknown")
    fid = edge.get("from_id", "")
    tid = edge.get("to_id", "")
    return f"{rt}-{fid}-{tid}"


# ── HTML template generation ─────────────────────────────────────────

def _build_template(
    elements_json: str,
    timestamp: str,
    total_nodes: int,
) -> str:
    """Build the full HTML string via f-string interpolation."""

    return (
        '<!DOCTYPE html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8"/>\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
        '<title>Pipeline Lineage &amp; Freshness</title>\n'
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>\n'
        '<style>\n'
        '  * { box-sizing: border-box; margin: 0; padding: 0; }\n'
        '  html, body { height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; }\n'
        '  header { padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; background: #1e293b; border-bottom: 1px solid #334155; }\n'
        '  header h1 { font-size: 1.25rem; font-weight: 600; }\n'
        '  header .meta { font-size: 0.8rem; color: #94a3b8; }\n'
        '  #cy { width: 100%; height: calc(100vh - 100px); background: #0f172a; }\n'
        '  footer { padding: 12px 24px; text-align: center; font-size: 0.75rem; color: #64748b; border-top: 1px solid #334155; background: #1e293b; }\n'
        '  .legend { position: absolute; top: 16px; left: 16px; background: rgba(30,41,59,0.95); border-radius: 8px; padding: 12px 16px; font-size: 0.8rem; z-index: 10; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }\n'
        '  .legend h3 { margin-bottom: 8px; color: #f1f5f9; font-size: 0.85rem; }\n'
        '  .legend-item { display: flex; align-items: center; gap: 8px; margin: 4px 0; }\n'
        '  .legend-dot { width: 12px; height: 12px; border-radius: 50%; }\n'
        '</style>\n'
        '</head>\n'
        '<body>\n'
        '\n'
        '<header>\n'
        '  <h1>Pipeline Lineage &amp; Freshness</h1>\n'
        f'  <span class="meta">Generated: {timestamp} &middot; Nodes: {total_nodes}</span>\n'
        '</header>\n'
        '\n'
        '<div id="cy"></div>\n'
        '\n'
        '<div class="legend">\n'
        '  <h3>Legend</h3>\n'
        f'  <div class="legend-item"><div class="legend-dot" style="background:{_COLOR_GREEN}"></div>Fresh</div>\n'
        f'  <div class="legend-item"><div class="legend-dot" style="background:{_COLOR_RED}"></div>Stale</div>\n'
        f'  <div class="legend-item"><div class="legend-dot" style="background:{_COLOR_GREY}"></div>No run data</div>\n'
        '  <hr style="border-color: #334155; margin: 6px 0;"/>\n'
        '  <div style="font-size:0.7rem;color:#94a3b8">Click a node to highlight its neighbors.</div>\n'
        '</div>\n'
        '\n'
        '<footer>\n'
        '  Dope &middot; MIT Licensed\n'
        '</footer>\n'
        '\n'
        '<script>\n'
        f'var elements = {elements_json};\n'
        '\n'
        "var cy = cytoscape({{\n"
        '  container: document.getElementById("cy"),\n'
        '  elements: elements,\n'
        '  style: [\n'
        '    {\n'
        '      selector: "node",\n'
        '      style: {\n'
        '        "label": "data(label)",\n'
        '        "background-color": "data(fill_color)",\n'
        '        "width": "mapData(font_size, 18, 42)",\n'
        '        "height": "mapData(font_size, 18, 42)",\n'
        '        "font-size": "10px",\n'
        '        "color": "#f1f5f9",\n'
        '        "text-halign": "center",\n'
        '        "text-valign": "center",\n'
        '        "text-outline-width": 2,\n'
        '        "text-outline-color": "#0f172a"\n'
        '      }\n'
        '    },\n'
        '    {\n'
        '      selector: "node[type=\'Model\']",\n'
        '      style: { "shape": "ellipse", "border-width": 2, "border-color": "#3b82f6" }\n'
        '    },\n'
        '    {\n'
        '      selector: "node[type=\'Connection\']",\n'
        '      style: { "shape": "hexagon", "border-width": 2, "border-color": "#a78bfa" }\n'
        '    },\n'
        '    {\n'
        '      selector: "node[type=\'Table\']",\n'
        '      style: { "shape": "round-rectangle", "border-width": 1, "border-color": "#475569" }\n'
        '    },\n'
        '    {\n'
        '      selector: "node[type=\'Product\']",\n'
        '      style: { "shape": "diamond", "border-width": 2, "border-color": "#f59e0b" }\n'
        '    },\n'
        '    {\n'
        '      selector: "edge",\n'
        '      style: {\n'
        '        "width": 1.5,\n'
        '        "line-color": "#475569",\n'
        '        "target-arrow-color": "#475569",\n'
        '        "target-arrow-shape": "triangle",\n'
        '        "curve-style": "bezier"\n'
        '      }\n'
        '    },\n'
        '    {\n'
        '      selector: ":selected",\n'
        '      style: { "border-width": 3, "border-color": "#fbbf24" }\n'
        '    },\n'
        '    {\n'
        '      selector: ".highlighted",\n'
        '      style: {\n'
        '        "line-color": "#fbbf24",\n'
        '        "target-arrow-color": "#fbbf24",\n'
        '        "background-color": "#fbbf24",\n'
        '        "border-color": "#fbbf24"\n'
        '      }\n'
        '    },\n'
        '    {\n'
        '      selector: ".dimmed",\n'
        '      style: { "opacity": 0.15 }\n'
        '    }\n'
        '  ],\n'
        '  layout: {\n'
        '    name: "cose",\n'
        '    idealEdgeLength: 60,\n'
        '    nodeOverlap: 20,\n'
        '    refresh: 20,\n'
        '    fit: true,\n'
        '    padding: 30,\n'
        '    randomize: false,\n'
        '    componentSpacing: 80,\n'
        '    nodeRepulsion: 450000\n'
        '  },\n'
        '  zoomingEnabled: true,\n'
        '  userZoomingEnabled: true,\n'
        '  panningEnabled: true,\n'
        '  userPanningEnabled: true,\n'
        '  boxSelectionEnabled: true,\n'
        '  selectionType: "single"\n'
        '});\n'
        '\n'
        'cy.on("tap", "node", function(evt) {\n'
        '  var node = evt.target;\n'
        '  cy.elements().removeClass("highlighted dimmed");\n'
        '  if (node.isSource() || node.isTarget()) {\n'
        '    var neighbourhood = node.neighborhood();\n'
        '    neighbourhood.addClass("highlighted");\n'
        '    var allOthers = cy.elements().difference(neighbourhood);\n'
        '    allOthers.addClass("dimmed");\n'
        '  } else {\n'
        '    node.addClass("highlighted");\n'
        '  }\n'
        '});\n'
        '\n'
        'cy.on("tap", function(evt) {\n'
        '  if (evt.target === cy) {\n'
        '    cy.elements().removeClass("highlighted dimmed").unselectify();\n'
        '  }\n'
        '});\n'
        '</script>\n'
        '\n'
        '</body>\n'
        '</html>'
    )
