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

"""Tests for PurePyGraph (add_node, add_edge, query, neighbors, save/load)."""

from __future__ import annotations

import pickle
import tempfile
from pathlib import Path

from dopedata.core.graph import PurePyGraph


class TestPurePyGraphBasic:
    """Test basic graph mutation and look-up operations."""

    def test_add_node(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "model.myproj.stg_orders")
        node = g.node("model.myproj.stg_orders")
        assert node is not None
        assert node["type"] == "dbtModel"
        assert node["id"] == "model.myproj.stg_orders"

    def test_add_node_with_props(self) -> None:
        g = PurePyGraph()
        g.add_node("FivetranConnection", "stripe", name="Stripe Billing")
        node = g.node("stripe")
        assert node is not None
        assert node["name"] == "Stripe Billing"

    def test_add_edge(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "a1")
        g.add_node("B", "b1")
        g.add_edge("DEPENDS_ON", "a1", "b1")
        assert len(g._edges) == 1
        edge = g._edges[0]
        assert edge["rel_type"] == "DEPENDS_ON"
        assert edge["from_id"] == "a1"
        assert edge["to_id"] == "b1"

    def test_add_edge_with_props(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "a1")
        g.add_node("B", "b1")
        g.add_edge("DEPENDS_ON", "a1", "b1", since="2026-01-01")
        assert g._edges[0]["since"] == "2026-01-01"

    def test_node_not_found(self) -> None:
        g = PurePyGraph()
        assert g.node("nonexistent") is None

    def test_overwrite_node_props(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "x1", value=1)
        g.add_node("A", "x1", value=2, extra=True)
        node = g.node("x1")
        assert node["value"] == 2
        assert node["extra"] is True


class TestPurePyGraphNeighbors:
    """Test neighbor queries in out/in directions."""

    def test_out_neighbors(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "a1")
        g.add_node("B", "b1")
        g.add_edge("DEPENDS_ON", "a1", "b1")
        out = g.neighbors("a1", direction="out")
        assert len(out) == 1
        assert out[0]["id"] == "b1"

    def test_in_neighbors(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "a1")
        g.add_node("B", "b1")
        g.add_edge("DEPENDS_ON", "a1", "b1")
        inp = g.neighbors("b1", direction="in")
        assert len(inp) == 1
        assert inp[0]["id"] == "a1"

    def test_no_neighbors(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "a1")
        assert g.neighbors("a1", direction="out") == []
        assert g.neighbors("a1", direction="in") == []

    def test_filtered_neighbors_by_rel_type(self) -> None:
        g = PurePyGraph()
        g.add_node("A", "a1")
        g.add_node("B", "b1")
        g.add_edge("DEPENDS_ON", "a1", "b1")
        g.add_edge("TESTS", "a1", "b1")
        out_deps = g.neighbors("a1", rel_type="DEPENDS_ON", direction="out")
        assert len(out_deps) == 1
        out_tests = g.neighbors("a1", rel_type="TESTS", direction="out")
        assert len(out_tests) == 1


class TestPurePyGraphQuery:
    """Test Cypher subset queries."""

    def test_query_single_node(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "m1", name="model_one")
        results = g.query("MATCH (n:dbtModel) RETURN n")
        assert len(results) == 1
        assert results[0]["n"]["id"] == "m1"

    def test_query_single_edge(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "a1", name="a")
        g.add_node("dbtModel", "b1", name="b")
        g.add_edge("DEPENDS_ON", "a1", "b1")
        results = g.query("MATCH (a)-[r:DEPENDS_ON]->(b) RETURN a, r, b")
        assert len(results) == 1
        assert results[0]["a"]["id"] == "a1"
        assert results[0]["b"]["id"] == "b1"
        assert results[0]["r"]["rel_type"] == "DEPENDS_ON"

    def test_query_with_where_string_literal(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "m1", name="alpha")
        g.add_node("dbtModel", "m2", name="beta")
        results = g.query("MATCH (n:dbtModel) WHERE n.name = 'alpha' RETURN n")
        assert len(results) == 1
        assert results[0]["n"]["name"] == "alpha"

    def test_query_with_where_param(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "m1", name="alpha")
        g.add_node("dbtModel", "m2", name="beta")
        results = g.query(
            "MATCH (n:dbtModel) WHERE n.name = $name RETURN n", name="beta"
        )
        assert len(results) == 1
        assert results[0]["n"]["name"] == "beta"

    def test_query_with_where_boolean(self) -> None:
        g = PurePyGraph()
        g.add_node("FivetranConnection", "c1", stale=True)
        g.add_node("FivetranConnection", "c2", stale=False)
        results = g.query("MATCH (n:FivetranConnection) WHERE n.stale = true RETURN n")
        assert len(results) == 1
        assert results[0]["n"]["id"] == "c1"

    def test_query_no_matches(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "m1", name="test")
        results = g.query("MATCH (n:dbtModel) WHERE n.name = 'nope' RETURN n")
        assert results == []

    def test_query_two_hop(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "a1", name="stg")
        g.add_node("dbtModel", "b1", name="int")
        g.add_node("dbtModel", "c1", name="fct")
        g.add_edge("DEPENDS_ON", "a1", "b1")
        g.add_edge("DEPENDS_ON", "b1", "c1")
        results = g.query(
            "MATCH (a)-[r]->(b)-[s]->(c) RETURN a, b, c"
        )
        assert len(results) == 1
        assert results[0]["a"]["id"] == "a1"
        assert results[0]["b"]["id"] == "b1"
        assert results[0]["c"]["id"] == "c1"

    def test_query_returns_only_requested_columns(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "m1", name="alpha", extra="hidden")
        results = g.query("MATCH (n:dbtModel) RETURN n.name")
        assert len(results) == 1
        assert "name" in results[0]
        assert results[0]["name"] == "alpha"


class TestPurePyGraphSaveLoad:
    """Test pickle-based save/load persistence."""

    def test_save_and_load(self) -> None:
        g = PurePyGraph()
        g.add_node("dbtModel", "m1", name="model_one")
        g.add_node("dbtModel", "m2", name="model_two")
        g.add_edge("DEPENDS_ON", "m1", "m2", since="2026-01-01")

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
            path = tmp.name

        try:
            g.save(path)

            g2 = PurePyGraph()
            g2.load(path)

            assert g2.node("m1")["name"] == "model_one"
            assert g2.node("m2")["name"] == "model_two"
            assert len(g2._edges) == 1
            assert g2._edges[0]["rel_type"] == "DEPENDS_ON"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_empty_graph_save_load(self) -> None:
        g = PurePyGraph()
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmp:
            path = tmp.name

        try:
            g.save(path)
            g2 = PurePyGraph()
            g2.load(path)
            assert len(g2._nodes) == 0
            assert len(g2._edges) == 0
        finally:
            Path(path).unlink(missing_ok=True)
