# BUILD DIRECTIVE: DopeData: Data Observatory Pipeline Explorability
## Apache 2.0 · Local FOSS Graph DB · Fivetran + dbt Lineage + Freshness  

---

## 0. MISSION

Build a single-repo, zero-credential, zero-pip-install demo that:

1. Ingests pipeline metadata for a **seed Fivetran connector** and its
   downstream dbt lineage into a local embedded graph database.
2. Computes **freshness** per node using a "last business day" rule.
3. Renders **three output views** in one demo script:
   - (a) raw Cypher query results (for engineers)
   - (b) tabular CSV/print dump (for non-technical stakeholders)
   - (c) static HTML graph visualization (for everyone)
4. Ships with a `make demo` target that runs end-to-end with **no
   network access, no credentials, no server processes.**
5. Is publish-ready under MIT on a personal GitHub account.

This is an **architecture-as-working-proof** artifact. The audience is a
mixed-technicality engineer meeting. The demo is the product.

---

## 1. HARD CONSTRAINTS

| Constraint | Detail |
|---|---|
| Python | 3.10+ (use `from __future__ import annotations` everywhere) |
| Zero-dep demo | `make demo` must succeed with **stdlib only**. No `pip install` required. |
| Graph backend default | **Pure-Python in-memory graph** (`dopedata.core.graph.GraphStore` protocol). This is the default and is the tested path. |
| Graph backend optional | **Kùzu** (`pip install kuzu`, Apache 2.0, embedded single-file `.db`, no server). Wired as an optional backend behind the same `GraphStore` protocol. Guarded by a `if KUZU_AVAILABLE:` import. |
| License | Apache 2.0. `LICENSE` file + `LICENSE_HEADER` in every `.py` file. |
| Lint/format | `ruff` + `mypy` in `pyproject.toml`. Not required for `make demo`, but present. |
| Packaging | `pyproject.toml` with `[project]` metadata. `uv`-compatible. No `setup.py`. |
| CI | Single GitHub Actions workflow: `pytest` on Python 3.11/3.12, `ruff check`, `mypy`. No matrix beyond those two versions. |
| No secrets in repo | All live-mode credentials via env vars. Snapshot mode uses committed CSV/JSON fixtures. |
| ShareDK compat | The core module exposes a `GraphStore` **Protocol** and a `PipelinePlugin` **ABC**. The Fivetran and dbt ingesters implement `PipelinePlugin`. This is the CORE+PLUGINS pattern; a `plugins/` dir with one file per connector/adapter is the expansion seam. Do NOT couple core to any specific backend or connector. |

---

## 2. REPO STRUCTURE (create exactly this)  
```
DopeData/
├── LICENSE # Apache 2.0 text
├── README.md # quickstart, < 120 lines
├── pyproject.toml
├── Makefile # make demo, make test, make live
├── .gitignore
├── .github/
│ └── workflows/
│ └── ci.yml
├── src/
│ └── dope/
│ ├── init.py # exposes version, GraphStore, PipelinePlugin
│ ├── core/
│ │ ├── init.py
│ │ ├── graph.py # GraphStore Protocol + PurePyGraph impl
│ │ ├── kuzu_backend.py # KuzuGraph impl (optional import)
│ │ ├── schema.py # Node/Edge type definitions, Cypher DDL
│ │ ├── freshness.py # last_business_day + stale flag
│ │ └── plugin.py # PipelinePlugin ABC
│ ├── plugins/
│ │ ├── init.py
│ │ ├── fivetran.py # FivetranPlugin: ingest from snapshot or REST
│ │ └── dbt.py # DbtPlugin: ingest from snapshot or Discovery API
│ ├── query/
│ │ ├── init.py
│ │ ├── lineage.py # seeded walk, upstream/downstream Cypher
│ │ ├── freshness_report.py# "which nodes are stale" tabular output
│ │ └── viz.py # static HTML (cytoscape.js inline) + CSV dump
│ └── cli/
│ ├── init.py
│ └── main.py # argparse: --seed, --backend, --view, --mode
├── data/
│ └── snapshots/
│ ├── fivetran_connections.csv
│ ├── fivetran_schemas.csv
│ ├── dbt_nodes.json # manifest.json subset
│ ├── dbt_run_results.json # run_results.json subset
│ └── fivetran_dbt_bridge.csv # connector_id → table → dbt model mapping
├── tests/
│ ├── init.py
│ ├── test_freshness.py
│ ├── test_graph.py
│ ├── test_plugins.py
│ └── test_lineage.py
├── scripts/
│ ├── run_demo.py # one-shot: load → build → 3 views
│ ├── seed_walk_demo.py # the 4-line loop over connector IDs (Phase 2)
│ └── export_snapshots.py # optional: pull live data → CSV/JSON
└── docs/
├── ARCHITECTURE.md # graph schema diagram (Mermaid), plugin flow
└── FRESHNESS_RULE.md # "last business day" definition + edge cases
```

---

## 3. GRAPH SCHEMA

Implement in `src/dopedata/core/schema.py`. The `PurePyGraph` uses plain
Python dicts and sets. The `KuzuGraph` backend uses equivalent Cypher DDL.

### 3.1 Node Types
```python
class NodeType(Enum):
    FIVETRAN_CONNECTION = "FivetranConnection"
    SNOWFLAKE_TABLE     = "SnowflakeTable"
    DBT_MODEL           = "dbtModel"
    DBT_TEST            = "dbtTest"
    DBT_SOURCE          = "dbtSource"
    DATA_PRODUCT        = "DataProduct"

# Required properties per node:
#   FIVETRAN_CONNECTION: id (str, e.g. "random_words"), name, status,
#     last_sync_start (ISO8601), last_sync_end (ISO8601), rows_synced (int),
#     freshness (date), stale (bool)
#   SNOWFLAKE_TABLE: schema (str), name (str), last_modified (ISO8601),
#     row_count (int), freshness (date), stale (bool)
#   DBT_MODEL: unique_id (str, e.g. "model.myproj.fct_orders"),
#     name, materialization (str: view|table|incremental),
#     run_status (str: success|error|warning|skipped),
#     start_time (ISO8601), end_time (ISO8601), row_count (int),
#     freshness (date), stale (bool)
#   DBT_TEST: unique_id, name, status (pass|fail|error),
#     associated_model (unique_id), freshness, stale
#   DATA_PRODUCT: name, owner, consumers (list[str], e.g. ["powerbi","qlik"])
```  

## 3.2 Edge Types
```
SYNC_TO      FIVETRAN_CONNECTION ──> SNOWFLAKE_TABLE
             (direction: connector lands into table)

PRODUCES     DBT_MODEL ──> SNOWFLAKE_TABLE
             (direction: model writes/overwrites table)

DEPENDS_ON   DBT_MODEL ──> DBT_MODEL
             (direction: downstream → upstream in DAG;
              i.e. model_B DEPENDS_ON model_A means A must run first)

TESTS        DBT_TEST ──> DBT_MODEL
             (direction: test validates model)

FEEDS        SNOWFLAKE_TABLE ──> DATA_PRODUCT
             (direction: table consumed by BI/ML product)

EXPOSED_BY   DATA_PRODUCT ──> DBT_MODEL
             (direction: data product is exposed by this model)
```

## 3.3 Cypher DDL (for Kùzu backend, kuzu_backend.py)
``` cypher
CREATE NODE TABLE FivetranConnection (
  id STRING PRIMARY KEY, name STRING, status STRING,
  last_sync_start STRING, last_sync_end STRING,
  rows_synced INT64, freshness STRING, stale BOOL
);
-- ... one CREATE NODE TABLE per type
-- ... one CREATE REL TABLE per edge type
```
The PurePyGraph does NOT need DDL — it uses typed Python objects.
Both backends implement the same GraphStore Protocol (§4).  

## 4. CORE: GraphStore Protocol + PurePyGraph  
`src/dopedata/core/graph.py:`
``` python 
from __future__ import annotations
from typing import Protocol, Any, Iterable

class GraphStore(Protocol):
    def add_node(self, node_type: str, node_id: str, **props: Any) -> None: ...
    def add_edge(self, rel_type: str, from_id: str, to_id: str, **props: Any) -> None: ...
    def query(self, cypher: str, **params: Any) -> list[dict]: ...
    def node(self, node_id: str) -> dict | None: ...
    def neighbors(self, node_id: str, rel_type: str | None = None,
                  direction: str = "out") -> list[dict]: ...
    def save(self, path: str) -> None: ...
    def load(self, path: str) -> None: ...

class PurePyGraph:
    """Zero-dependency in-memory graph. Dict-based. Implements GraphStore."""
    # internal: _nodes: dict[str, dict], _edges: dict[str, list[dict]]
    # query() supports a MINIMAL Cypher subset:
    #   MATCH (n:Type) RETURN n
    #   MATCH (a)-[r:REL]->(b) RETURN a, r, b
    #   MATCH (a)-[r:REL]->(b)-[s:REL]->(c) RETURN a, b, c   (1-hop walk)
    #   WHERE n.id = $id
    #   WHERE n.stale = true
    # For anything beyond this, raise NotImplementedError with a message
    # pointing to the Kuzu backend. The PurePyGraph is for demo, not production.
```
The PurePyGraph.query() does NOT need to be a real Cypher parser.
Implement a pattern-matched mini-interpreter that handles the 4 query
shapes above. Log a warning for anything else. This keeps the demo
zero-dep while proving the graph concept.

The KuzuGraph in kuzu_backend.py passes the same Cypher strings to
Kùzu's actual query engine. Guard the import:
``` python 
try:
    import kuzu
    KUZU_AVAILABLE = True
except ImportError:
    KUZU_AVAILABLE = False
```  
GraphStore is a Protocol so both are structurally typed. mypy
verifies both conform. No ABC, no registration, no factory — structural
typing only.  

## 5. FRESHNESS MODULE
`src/dopedata/core/freshness.py:`
``` python
from __future__ import annotations
from datetime import date, timedelta
from zoneinfo import ZoneInfo

US_HOLIDAYS_2026: frozenset[date] = frozenset([
    date(2026,1,1),   # New Year's Day
    date(2026,1,19),  # MLK Day
    date(2026,2,16),  # Presidents Day
    date(2026,5,25),  # Memorial Day
    date(2026,6,19),  # Juneteenth
    date(2026,7,4),   # Independence Day
    date(2026,9,7),   # Labor Day
    date(2026,10,12), # Columbus Day
    date(2026,11,11), # Veterans Day
    date(2026,11,26), # Thanksgiving
    date(2026,12,25), # Christmas
])

def last_business_day(today: date | None = None,
                      holidays: frozenset[date] = US_HOLIDAYS_2026) -> date:
    """Return the most recent calendar day that is a Mon-Fri and not in
    `holidays`. Walk backward from `today` until found. O(1) in practice
    since holidays are sparse."""

def is_stale(last_run_end: date, as_of: date | None = None,
              holidays: frozenset[date] = US_HOLIDAYS_2026) -> bool:
    """A node is stale if its last successful run_end is strictly before
    the last business day at 00:00. 'last business day' = the most recent
    non-weekend, non-holiday day on or before `as_of` (default: today)."""

def freshness_date(last_run_end: date, as_of: date | None = None) -> date:
    """Return last_business_day if node is stale (flag for reporting),
    else return last_run_end. This is the 'freshness' field value."""  
```
Edge cases to handle and test:

* `last_run_end` is a `datetime`, not a `date` → extract `.date()`.
* `last_run_end` is None (model never ran) → always stale.
* `as_of` is a Saturday → walk back to Friday unless Friday is a holiday.
* `as_of` is a US holiday → walk back to the prior weekday.
* Timezone: treat all timestamps as UTC for comparison. ZoneInfo
  is available in stdlib (Python 3.9+). Do not use pytz.  

*Do NOT use the holidays library.* It's not stdlib. Hardcode the 
2026 list as above and document that the user can swap in holidays
for production. Keep the demo zero-dep.

## 6. PLUGINS (Ingestion)
`src/dopedata/plugins/fivetran.py` and `src/dopedata/plugins/dbt.py`.

Both implement `PipelinePlugin` from `core/plugin.py`:  
``` python
class PipelinePlugin(ABC):
    @abstractmethod
    def ingest(self, store: GraphStore, mode: str = "snapshot",
               **kwargs) -> int:
        """Load nodes/edges into `store`. Return count of nodes created.
        mode='snapshot' reads from data/snapshots/.
        mode='live'    calls the real API (requires credentials in env)."""
        ...  
```

### 6.1 FivetranPlugin — snapshot mode
Read `data/snapshots/fivetran_connections.csv`. Columns:
`connector_id`, `name`, `status`, `last_sync_start`, `last_sync_end`, `rows_synced`

Read `data/snapshots/fivetran_schemas.csv`. Columns:
`connector_id`, `table_schema`, `table_name`

Read `data/snapshots/fivetran_dbt_bridge.csv`. Columns:
`connector_id`, `table_schema`, `table_name`, `dbt_unique_id`

For each connection row:

* Create `FIVETRAN_CONNECTION` node. Compute `freshness` and `stale`
from `last_sync_end` via `freshness.py`.
* For each schema row matching `connector_id`: create `SNOWFLAKE_TABLE`
node with `last_modified = last_sync_end` (approximation for demo),
`row_count` from connection's `rows_synced` (or 0 if unknown).
* Add `SYNC_TO` edge.
* For each bridge row: link `SNOWFLAKE_TABLE` → `DBT_MODEL` via
the dbt plugin's node (create if absent). No edge type needed for
this link — the `PRODUCES` edge from dbt covers it. The bridge
CSV is the join key.  

### 6.2 FivetranPlugin — live mode (optional, guarded)
If `FIVETRAN_API_TOKEN` and `FIVETRAN_ACCOUNT` env vars are set:

* `GET /v1/connections?status=active` → list connections
* `GET /v1/connections/{id}` → per-connection: status,
  last_sync, latest_sync with start_time, end_time,
  rows_synced, rows_errored
* `GET /v1/connections/{id}/schema` → table list
* Parse into the same node/edge shape. Wrap in try/except — on
  any API error, print a warning and fall back to snapshot.

### 6.3 DbtPlugin — snapshot mode
Read `data/snapshots/dbt_nodes.json` (subset of `manifest.json`):
Each entry has: `unique_id` (e.g. "model.myproj.fct_orders"),
`name`, `resource_type` (model|test|source|exposure),
`materialized` (view|table|incremental),
`depends_on` → {"nodes": ["model.myproj.stg_orders", ...]},
`config` → {"materialized": "incremental"}

Read `data/snapshots/dbt_run_results.json` (subset of
`run_results.json`):
Each entry has: `unique_id`, `status` (success|error|warning|
skipped), `started_at` (ISO8601), `finished_at` (ISO8601),
`execution_time` (float, seconds),
`unique_id` of associated model for tests.

For each node in `dbt_nodes.json`:
1. Create node of appropriate type (DBT_MODEL, DBT_TEST,
DBT_SOURCE, or DATA_PRODUCT for exposures).
2. For DBT_MODEL: look up `dbt_run_results.json` by `unique_id`
for `start_time`, `end_time`, `run_status`, `row_count`
(use `execution_time` × estimated throughput if `row_count`
absent; document this approximation).
3. For DBT_MODEL: create DEPENDS_ON edges from `depends_on.nodes`
(direction: this model DEPENDS_ON each upstream model).
4. For DBT_TEST: create TESTS edge to its associated model.
5. For exposures: create EXPOSED_BY edge and a DATA_PRODUCT node.  

### 6.4 DbtPlugin — live mode (optional, guarded)
If `DBT_CLOUD_HOST` and `DBT_CLOUD_TOKEN` env vars are set:

* GET {host}/api/v2/accounts/{account_id}/environments/{env_id}/nodes → node definitions 
* GET {host}/api/v2/accounts/{account_id}/environments/{env_id}/nodes with include=run_results → execution metadata 
* GET {host}/api/v2/accounts/{account_id}/environments/{env_id}/lineage → native lineage graph 
* Parse into same node/edge shape. Same try/except fallback to snapshot.

## 7. QUERY LAYER
### 7.1 `lineage.py` — Seeded Walk  
``` python 
def seed_walk(store: GraphStore, seed_connector_id: str,
              depth_up: int = 3, depth_down: int = 3,
              backend: str = "pure") -> dict:
    """Given a Fivetran connector ID (e.g. 'random_words'), walk:
    UP:   FIVETRAN_CONNECTION <-[SYNC_TO]- SNOWFLAKE_TABLE
    DOWN: SNOWFLAKE_TABLE ->[PRODUCES]- DBT_MODEL ->[DEPENDS_ON]- DBT_MODEL...
    Also pull DBT_TEST nodes for any model in the walk.
    Return: { 'nodes': [...], 'edges': [...], 'stale_count': int }
    """
```
For `PurePyGraph`: implement as breadth-first dict traversal.
For `KuzuGraph`: emit Cypher:  
``` cypher  
MATCH path = (conn:FivetranConnection {id: $seed})<-[:SYNC_TO]-(tbl:SnowflakeTable)
  -[:PRODUCES|DEPENDS_ON*1..3]->(m:dbtModel)
RETURN path  
```
Use `*1..3` for variable-length path. Guard with `try/except` for
`PurePyGraph` (which doesn't support `*`).

### 7.2 `freshness_report.py` — Tabular View  
``` python 
def stale_report(store: GraphStore, as_of: date | None = None) -> str:
    """Return a formatted text table:
    NODE_ID | TYPE | LAST_RUN_END | FRESHNESS | STALE | ROWS
    One row per node. Stale rows marked with [STALE] prefix.
    Group by node type. This is the 'excel brain' view — flat, scannable,
    no graph required to understand.
    """  
```
Also export to CSV at data/snapshots/freshness_report.csv so the
non-technical audience can open it in Excel/Sheets without running
anything.

### 7.3 viz.py — Static HTML
Generate `data/snapshots/lineage_graph.html`. No server. No build
step. Double-click to open in any browser.

Implementation: inline a single self-contained HTML file with:

cytoscape.js inlined from a CDN URL embedded as a `<script src>`
tag (CDN is fine for a demo; document that for air-gapped use they
can vendor the JS).
Graph data as a JSON blob embedded in a `<script>` tag.
Layout: `cose` (force-directed) for the full graph, `breadthfirst`
for the seed walk view.
Color coding: green = fresh, red = stale, grey = no run data.
Node labels show `node.name`. Clicking a node highlights its
immediate neighbors.
A legend in the top-left.
Title: "Pipeline Lineage & Freshness — [seed connector name]"
Footer: "Generated by dope · Apache 2.0 · [timestamp]"
The HTML file must be **< 200KB** so it's fast to open and easy to
share. If the graph is > 100 nodes, sample to the seed walk subtree.

## 8. CLI
`src/dopedata/cli/main.py` — argparse, no `click`/`typer` (zero-dep):  
``` bash  
python -m dopedata --seed random_words --backend pure --view all
python -m dopedata --seed random_words --backend kuzu  --view cypher
python -m dopedata --seed random_words --backend kuzu  --view html
python -m dopedata --seed random_words --mode live --backend pure
python -m dopedata --all-connectors --backend pure --view csv  
```
Args:

* `--seed ID` : single Fivetran connector ID (default: from env or first in snapshot)
* `--all-connectors` : loop over all connectors in snapshot (the Phase 2 scale-up)
* `--backend {pure,kuzu}` : graph backend (default: pure)
* `--view {all,cypher,tabular,html}` : output view (default: all)
* `--mode {snapshot,live}` : data source (default: snapshot)
* `--out-dir DIR` : where to write outputs (default: `data/snapshots/`)
* `--as-of DATE` : override "today" for freshness computation (ISO date)

`--view all` : runs all three views in sequence and prints to stdout:  
1. Cypher query + result rows (nerd view)
2. Tabular freshness report (NPC view)
3. "Open lineage_graph.html in your browser" message + file path (homie view)  


## 9. SNAPSHOT FIXTURES (create realistic demo data)
`data/snapshots/fivetran_connections.csv` — 3 connectors:
```
connector_id,name,status,last_sync_start,last_sync_end,rows_synced
random_words,Random Words,active,2026-08-14T08:00:00Z,2026-08-14T08:03:12Z,4821
stripe,Stripe Billing,active,2026-08-14T06:00:00Z,2026-08-14T06:47:05Z,12043
salesforce,SFDC CRM,active,2026-08-12T02:00:00Z,2026-08-12T02:31:00Z,889
```
Note: `salesforce` last ran 2026-08-12. If demo runs on 2026-08-15
(Thursday), `salesforce` is stale (last business day = 2026-08-14,
and 08-12 < 08-14). `random_words` and `stripe` ran on 08-14 → fresh.
This is intentional: one stale node makes the demo visible.

`fivetran_schemas.csv` — 6-8 tables across the 3 connectors.
`fivetran_dbt_bridge.csv` — maps tables to dbt models.

`dbt_nodes.json` — ~12 nodes:
* 3 `stg_` (staging) models, materialized as `view`
* 2 `int_` (intermediate) models, `view`
* 2 `fct_` (fact) models, `table` or `incremental`
* 3 dimension models (`dim_`), `table`
* 2 `test` nodes (unique + not_null)
* 1 `exposure` → `DataProduct` (PowerBI dashboard)
Lineage: `stg_orders → int_orders → fct_orders → dim_products → exposure`
`stg_customers → int_customers → fct_orders` (shared downstream — this is
the interconnection that makes the graph non-trivial).
`stripe connector → stg_stripe_events → int_stripe_revenue →
fct_stripe_revenue`.

`dbt_run_results.json` — matching run records. One `fct_` model has
`status: error` to show a failure node. One `stg_` model has
`status: skipped`.

`fivetran_dbt_bridge.csv` — the join:
```
connector_id,table_schema,table_name,dbt_unique_id
random_words,fivetran_random_words,words,model.myproj.stg_random_words
stripe,fivetran_stripe,charges,model.myproj.stg_stripe_events
stripe,fivetran_stripe,invoices,model.myproj.stg_stripe_invoices
salesforce,fivetran_sf,opportunities,model.myproj.stg_sf_opportunities
```

## 10. DEMO SCRIPT (scripts/run_demo.py)
``` python 
#!/usr/bin/env python3
"""One-shot demo: load snapshots → build graph → run all 3 views.
Run: python scripts/run_demo.py
Exit: 0 on success. Prints instructions for opening the HTML.
"""
```
It should:  
1. Load both plugins in snapshot mode.
2. Run `seed_walk` for `random_words` (the primary demo path).
3. Run `seed_walk` for `stripe` (shows a second independent path).
4. Print the Cypher queries + results to stdout.
5. Print the tabular freshness report to stdout.
6. Write `lineage_graph.html` and print its path.
7. Write `freshness_report.csv`.
8. Print a 3-line summary: "N nodes, M edges, K stale." Open `lineage_graph.html` for the visual. Open `freshness_report.csv` for the table.
9. Total runtime: < 2 seconds. It's a demo, not an ETL job.

## 11. ACCEPTANCE CRITERIA
The build is done when ALL of these pass:


[ ] make demo runs successfully with zero pip installs, zero
network, zero credentials. Prints 3 views. Exits 0.

[ ] lineage_graph.html opens in Chrome/Firefox/Safari and renders
the graph with color-coded freshness. File size < 200KB.

[ ] freshness_report.csv opens in Excel/Sheets and shows the stale
node flagged.

[ ] pytest -v passes. All 4 test files. No skips.

[ ] ruff check src/ reports zero errors.

[ ] mypy src/dopedata/ passes with no errors on the PurePyGraph
and KuzuGraph conforming to GraphStore.

[ ] python -m dopedata --backend kuzu --seed random_words works when
Kùzu is installed (skip gracefully when it's not).

[ ] LICENSE is the full Apache 2.0 text. Every .py file has the
license header.

[ ] README.md has a < 30-second quickstart: clone → make demo →
open HTML. No more than 120 lines.

[ ] ARCHITECTURE.md has a Mermaid diagram of the graph schema and
a Mermaid sequence diagram of the plugin ingestion flow.

[ ] FRESHNESS_RULE.md documents the "last business day" definition,
the edge cases, and how to swap in the holidays library for
production.

[ ] No TODO, no pass, no # placeholder in any non-test file.
[ ] The demo is complete, not a skeleton. 
[ ] git log shows a single squashed commit with a clean message:
```
"feat: pipeline explorability — Fivetran + dbt lineage, freshness,
Kùzu backend, static viz" or equivalent.
```

## 12. ITERATION PROTOCOL
This directive is the `Architect output`. Feed it to the Coder model
(Qwen 2.5 Coder 32B or 72B via Ollama). The Coder produces the code.

Then feed the output to the `Critical Reviewer` (recommended:
`DeepSeek R1 70B` via Ollama if available locally; otherwise
`Llama 3.1 70B` or `Qwen 2.5 72B` — the reviewer needs strong
reasoning, not fast inference). The Reviewer checks:

1. __Does it meet every acceptance criterion?__ (checklist in §11)
2. __Is the graph schema correct?__ (edge directions, node properties,
Cypher DDL matches Python objects)
3. __Is the freshness logic correct?__ (edge cases in §5, timezone
handling, holiday list matches 2026 US federal calendar)
4. __Is the snapshot data internally consistent?__ (bridge CSV joins
to actual node IDs in dbt_nodes.json; no dangling references)
5. __Is the HTML self-contained?__ (no external JS/CSS dependencies
except the one cytoscape CDN; no API calls; no server needed)
6. __Is the zero-dep promise held?__ (no imports outside stdlib in the
pure backend path; Kùzu import is guarded; snowflake connector is
guarded)
7. __Is the plugin pattern clean?__ (CORE has zero knowledge of Fivetran, dbt, Kùzu, or Snowflake; all coupling is in `plugins/`)  

The Reviewer outputs two things:
* `Summary` (1-2 paragraphs): what's good, what's broken, risk
assessment for the demo.
* `Directives` (numbered list of specific code changes, with file paths and line numbers if possible). These feed back to the Coder for the next iteration.

__Termination__: 3 iterations max, or until the Reviewer's Summary
says "ready for demo." If it's not ready after 3 iterations, the
issue is likely architectural — re-run the Architect with the
Reviewer's Summary as input to produce a v2 directive.  

__Do NOT loop more than 3 times without a human reading the Summary.__
The Coder can get into a local minimum. The human (you) is the
convergence check.

13. NOTES FOR THE CODER MODEL
* Use `from __future__ import annotations` in every file.
* Use `pathlib.Path`, not `os.path`.
* Use `dataclass` for data carriers. Not `pydantic` (zero-dep).
* Type hints everywhere. `mypy --strict` should pass on `core/`.
* The `PurePyGraph.query()` mini-interpreter is the hardest part.
  * Implement it as a dict-based pattern matcher, not a real parser.
  * Support exactly the 4 query shapes in §4.
  * Raise `NotImplementedError` for anything else with a helpful message.
  * This is intentional — it proves the concept without the dependency.
* The Kùzu backend passes Cypher strings directly to `kuzu.query()`.
  * No translation layer.
* `cytoscape.js` for the HTML viz. Inline the data as JSON in a
  `<script>` tag. Layout: `cose`. Color: green (#22c55e) fresh,
  red (#ef4444) stale, grey (#9ca3af) no data.
* The `fivetran_dbt_bridge.csv` is the __critical join file__.
  * Without it, the Fivetran and dbt graphs are disconnected.
* Make sure the demo data has valid joins.
* Do not add a `requirements.txt`. Use `pyproject.toml` only. To be a purely UV driven project.
* Do not add Docker. Do not add Makefile targets beyond
  `demo`, `test`, `live`, `clean`.
* Do not add a web server. Do not add FastAPI/Flask/Gradio.
* The HTML is static. That's the point.
