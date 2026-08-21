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

"""dbt plugin – ingest manifest & run-result data into the graph."""

from __future__ import annotations

import datetime
import json
import logging
import os
import pathlib
from typing import TYPE_CHECKING, Any

from dope.core.freshness import freshness_date, is_stale
from dope.core.plugin import PipelinePlugin
from dope.core.schema import NodeType

if TYPE_CHECKING:
    from dope.core.graph import GraphStore

logger = logging.getLogger(__name__)


def _resolve_snapshot_dir() -> pathlib.Path:
    """Return the directory containing snapshot CSV/JSON files."""
    env_val = os.environ.get("DOPE_SNAPSHOT_DIR")
    if env_val:
        return pathlib.Path(env_val)
    candidate = pathlib.Path(__file__).resolve().parents[3] / "data" / "snapshots"
    if candidate.exists():
        return candidate
    return pathlib.Path.cwd() / "data" / "snapshots"


class DbtPlugin(PipelinePlugin):
    """Ingest dbt manifest and run-result data into a :class:`GraphStore`.

    Supports two ingestion modes:

    * **snapshot** (default) – reads JSON files from the snapshot directory.
    * **live** – queries the DBT Cloud API.
    """

    def __init__(self, snapshot_dir: pathlib.Path | None = None) -> None:
        """Initialise with an optional snapshot directory override."""
        self.snapshot_dir: pathlib.Path | None = snapshot_dir

    def ingest(
        self,
        store: GraphStore,
        mode: str = "snapshot",
        **kwargs: Any,
    ) -> int:
        snap_dir = kwargs.get("snapshot_dir") or self.snapshot_dir or _resolve_snapshot_dir()

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

    def _ingest_snapshot(
        self, store: GraphStore, snapshot_dir: pathlib.Path
    ) -> int:
        """Read manifest and run-result JSON files and build the graph."""
        manifest_path = snapshot_dir / "dbt_nodes.json"
        results_path = snapshot_dir / "dbt_run_results.json"

        if not manifest_path.exists():
            logger.warning("Manifest file not found: %s", manifest_path)
            return 0

        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read manifest: %s", exc)
            return 0

        run_results_list: list[dict[str, Any]] = []
        if results_path.exists():
            try:
                with open(results_path, encoding="utf-8") as fh:
                    data = json.load(fh)
                    # Handle both top-level list and dict-with-key shapes
                    if isinstance(data, list):
                        run_results_list = data
                    elif isinstance(data, dict):
                        for key in ("results", "run_results", "data"):
                            val = data.get(key)
                            if isinstance(val, list):
                                run_results_list = val
                                break
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read run results: %s", exc)

        # Build lookup of run results by unique_id
        run_by_id: dict[str, dict[str, Any]] = {}
        for rr in run_results_list:
            uid = rr.get("unique_id") or rr.get("node_unique_id")
            if uid:
                run_by_id[uid] = rr

        # Determine what form the manifest nodes are in
        nodes_data: list[dict[str, Any]] = []
        if isinstance(manifest, list):
            nodes_data = manifest
        elif isinstance(manifest, dict):
            for key in ("nodes", "data", "sources", "models"):
                val = manifest.get(key)
                if isinstance(val, list):
                    nodes_data.extend(val)

        # Also grab exposures separately
        exposure_data: list[dict[str, Any]] = []
        if isinstance(manifest, dict):
            exp_val = manifest.get("exposures") or manifest.get("data", {}).get("exposures")
            if isinstance(exp_val, dict):
                for _k, v in exp_val.items():
                    exposure_data.append(v)
            elif isinstance(exp_val, list):
                exposure_data.extend(exp_val)

        node_count = 0

        # Track model ids for EXPOSED_BY edges
        models_seen: set[str] = set()

        for node in nodes_data:
            uid = node.get("unique_id", "")
            if not uid:
                continue

            resource_type = (node.get("resource_type") or "").lower()
            name = node.get("name", uid)
            package_name = node.get("package_name", "")
            depends_on_nodes: list[str] = []
            config_materialized: str | None = None

            # Parse depends_on
            depends_raw = node.get("depends_on")
            if isinstance(depends_raw, dict):
                depends_on_nodes = depends_raw.get("nodes", [])
            elif isinstance(depends_raw, list):
                depends_on_nodes = depends_raw

            # Parse config
            config = node.get("config") or {}
            if isinstance(config, dict):
                config_materialized = config.get("materialized")

            # Map resource_type → NodeType
            type_map: dict[str, str] = {
                "model": NodeType.DBT_MODEL.value,
                "test": NodeType.DBT_TEST.value,
                "source": NodeType.DBT_SOURCE.value,
            }
            node_type_str = type_map.get(resource_type)

            if not node_type_str:
                continue

            # Look up run result for this node
            rr = run_by_id.get(uid)

            # Create the node
            props: dict[str, Any] = {
                "name": name,
                "package_name": package_name,
            }

            if resource_type in ("model", "test"):
                start_time: str | None = None
                end_time: str | None = None
                run_status: str | None = None
                if rr:
                    start_time = rr.get("started_at") or rr.get("timestamp")
                    end_time = rr.get("finished_at") or rr.get("execution_started_at")
                    run_status = rr.get("status")

                props["start_time"] = start_time
                props["end_time"] = end_time
                props["run_status"] = run_status

            if node_type_str == NodeType.DBT_MODEL.value:
                models_seen.add(uid)
                materialized = config_materialized or "view"
                props["materialization"] = materialized

                # Compute freshness from finished_at
                end_ts = end_time
                if isinstance(end_ts, str) and end_ts:
                    try:
                        dt = self._parse_iso_timestamp(end_ts)
                        f_date = freshness_date(dt)
                        stale_flag = is_stale(dt)
                    except (ValueError, TypeError):
                        f_date = None
                        stale_flag = True
                else:
                    f_date = None
                    stale_flag = True

                props["freshness"] = str(f_date) if f_date else None
                props["stale"] = stale_flag

            elif node_type_str == NodeType.DBT_TEST.value:
                test_type = node.get("test_metadata", {}).get("type", "generic") if isinstance(node.get("test_metadata"), dict) else ""
                props["test_type"] = test_type
                props["status"] = run_status or "unknown"
                execution_time = rr.get("execution_time") if rr else None
                if isinstance(execution_time, (int, float)):
                    props["execution_time_ms"] = int(execution_time * 1000)

                end_ts = end_time
                if isinstance(end_ts, str) and end_ts:
                    try:
                        dt = self._parse_iso_timestamp(end_ts)
                        f_date = freshness_date(dt)
                        stale_flag = is_stale(dt)
                    except (ValueError, TypeError):
                        f_date = None
                        stale_flag = True
                else:
                    f_date = None
                    stale_flag = True

                props["freshness"] = str(f_date) if f_date else None
                props["stale"] = stale_flag

            elif node_type_str == NodeType.DBT_SOURCE.value:
                loaded_at = node.get("loaded_at") or (rr.get("finished_at") if rr else None)
                props["loaded_at"] = loaded_at
                if isinstance(loaded_at, str) and loaded_at:
                    try:
                        dt = self._parse_iso_timestamp(loaded_at)
                        f_date = freshness_date(dt)
                        stale_flag = is_stale(dt)
                    except (ValueError, TypeError):
                        f_date = None
                        stale_flag = True
                else:
                    f_date = None
                    stale_flag = True

                props["freshness"] = str(f_date) if f_date else None
                props["stale"] = stale_flag

            store.add_node(node_type_str, uid, **props)
            node_count += 1

            # Add edges for models
            if resource_type == "model":
                for upstream_uid in depends_on_nodes:
                    store.add_edge("DEPENDS_ON", uid, upstream_uid)

            # Add TESTS edge for tests (to the parent model)
            if resource_type == "test":
                # Determine the associated model id
                # test_metadata.node_unique_id or depends_on the node itself
                test_meta = node.get("test_metadata") or {}
                attached_to: str | None = None
                if isinstance(test_meta, dict):
                    attached_to = test_meta.get("attached_node") or test_meta.get(
                        "node_value"
                    )
                if not attached_to:
                    # Try to find from depends_on — last item could be the model
                    if depends_on_nodes:
                        for dep in reversed(depends_on_nodes):
                            dep_type = ""
                            for n in nodes_data:
                                if n.get("unique_id") == dep:
                                    dep_type = (n.get("resource_type") or "").lower()
                                    break
                            if dep_type == "model":
                                attached_to = dep
                                break
                    # Fallback: use test's own uid minus the suffix
                    if not attached_to:
                        parts = uid.split(".")
                        if len(parts) >= 3 and parts[-2] in ("test", "analysis"):
                            attached_to = ".".join(parts[:-2])

                if attached_to:
                    store.add_edge("TESTS", uid, attached_to)

        # Handle exposures → DATA_PRODUCT nodes + EXPOSED_BY edges
        for exposure in exposure_data:
            exp_uid = exposure.get("unique_id", "")
            if not exp_uid:
                continue

            name = exposure.get("name", exp_uid)
            owner = exposure.get("owner", {}).get("email") or exposure.get(
                "owner", {}
            ).get("name") if isinstance(exposure.get("owner"), dict) else None
            description = exposure.get("description", "")

            # Determine consumers from type
            exp_type = (exposure.get("type") or "").lower()
            consumers: list[str] = [exp_type] if exp_type else []

            store.add_node(
                NodeType.DATA_PRODUCT.value,
                exp_uid,
                name=name,
                description=description,
                owner=owner,
                consumers=",".join(consumers),
                freshness=None,
                stale=False,
            )
            node_count += 1

            # Create EXPOSED_BY edges from referenced models
            depends_raw = exposure.get("depends_on") or {}
            model_refs: list[str] = []
            if isinstance(depends_raw, dict):
                model_refs = depends_raw.get("nodes", [])
            elif isinstance(depends_raw, list):
                model_refs = depends_raw

            for ref_uid in model_refs:
                store.add_edge("EXPOSED_BY", exp_uid, ref_uid)

        # Post-processing: create PRODUCES edges from dbtModel/dbtSource to
        # SnowflakeTable nodes whose names appear in the node's depends_on.
        # This connects tables → models back to their upstream source connectors.
        for node in nodes_data:
            uid = node.get("unique_id", "")
            if not uid:
                continue
            rtype = (node.get("resource_type") or "").lower()
            if rtype not in ("model", "source"):
                continue
            depends_raw = node.get("depends_on") or {}
            dep_nodes: list[str] = []
            if isinstance(depends_raw, dict):
                dep_nodes = depends_raw.get("nodes", [])
            elif isinstance(depends_raw, list):
                dep_nodes = depends_raw

            for dep_uid in dep_nodes:
                # Check if this dependency is a SnowflakeTable node already in the store
                existing = store.node(dep_uid)
                if existing and existing.get("type") == NodeType.SNOWFLAKE_TABLE.value:
                    store.add_edge("PRODUCES", uid, dep_uid)

        return node_count

    # ── live mode ───────────────────────────────────────────────────────

    def _ingest_live(self, store: GraphStore) -> int:
        """Query DBT Cloud API for project/run data."""
        host = os.environ.get("DBT_CLOUD_HOST")
        token = os.environ.get("DBT_CLOUD_TOKEN")

        if not host or not token:
            raise EnvironmentError(
                "Live mode requires DBT_CLOUD_HOST and DBT_CLOUD_TOKEN env vars."
            )

        node_count = 0

        # Fetch run details for latest job
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }
        import urllib.error
        import urllib.request

        try:
            latest_run_url = f"{host}/api/v3/runs/"
            req = urllib.request.Request(latest_run_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                run_data = json.loads(resp.read().decode("utf-8"))

            runs = run_data.get("results", {}).get("data") or run_data.get(
                "data", {}
            ).get("data") or []
            if not runs:
                return 0

            # Get the latest completed run
            latest_run = None
            for r in sorted(runs, key=lambda x: x.get("finished_at", ""), reverse=True):
                if r.get("status") == 30:  # success status code per DBT Cloud API
                    latest_run = r
                    break
            if not latest_run:
                # Use the most recent run regardless of status
                latest_run = runs[0]

            run_id = latest_run.get("id")
            run_status = "completed" if latest_run.get("status") == 30 else "failed"
            started_at = latest_run.get("started_at")
            finished_at = latest_run.get("finished_at")
            execution_time = latest_run.get("elapsed")

            # Fetch run steps (individual model executions)
            steps_url = f"{host}/api/v3/run-steps/?run_id={run_id}"
            req_steps = urllib.request.Request(steps_url, headers=headers)
            with urllib.request.urlopen(req_steps, timeout=30) as resp:  # noqa: S310
                step_data = json.loads(resp.read().decode("utf-8"))

            steps = step_data.get("results", {}).get("data") or step_data.get(
                "data", {}
            ).get("data") or []

            for step in steps:
                model_name = step.get("unique_id", "") or step.get(
                    "name", f"model-{step.get('id', 'unknown')}"
                )
                uid = model_name if "." in model_name else f"dbt_model.{model_name}"

                step_status = step.get("status")
                if step_status == 30:
                    status_str = "success"
                elif step_status == 40:
                    status_str = "failed"
                else:
                    status_str = "unknown"

                start_ts = step.get("started_at") or started_at
                end_ts = step.get("finished_at") or finished_at

                if end_ts:
                    try:
                        dt = self._parse_iso_timestamp(end_ts)
                        f_date = freshness_date(dt)
                        stale_flag = is_stale(dt)
                    except (ValueError, TypeError):
                        f_date = None
                        stale_flag = True
                else:
                    f_date = None
                    stale_flag = True

                store.add_node(
                    NodeType.DBT_MODEL.value,
                    uid,
                    name=model_name.rsplit(".", 1)[-1] if "." in model_name else model_name,
                    package_name="dbt_cloud",
                    materialization="table",
                    start_time=start_ts,
                    end_time=end_ts,
                    run_status=status_str,
                    freshness=str(f_date) if f_date else None,
                    stale=stale_flag,
                )
                node_count += 1

        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            raise RuntimeError(f"Failed to query DBT Cloud API: {exc}") from exc

        return node_count

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_iso_timestamp(value: str) -> datetime.datetime:
        """Parse an ISO-8601 timestamp string into a naive datetime."""
        value = value.strip().rstrip("Z")
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
