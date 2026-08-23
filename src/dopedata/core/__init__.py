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

"""Core graph and schema infrastructure."""

from __future__ import annotations

from dopedata.core.freshness import (  # noqa: E402
    US_HOLIDAYS_2026,
    freshness_date,
    is_stale,
    last_business_day,
)
from dopedata.core.graph import GraphStore, PurePyGraph  # noqa: E402
from dopedata.core.kuzu_backend import (  # noqa: E402
    KUZU_AVAILABLE,
    KuzuGraph,
    get_graph_store,
)
from dopedata.core.plugin import PipelinePlugin  # noqa: E402
from dopedata.core.schema import CYPHER_DDL, EdgeType, NodeType  # noqa: E402

__all__: list[str] = [
    "CYPHER_DDL",
    "EdgeType",
    "GraphStore",
    "KUZU_AVAILABLE",
    "KuzuGraph",
    "NodeType",
    "PipelinePlugin",
    "PurePyGraph",
    "US_HOLIDAYS_2026",
    "freshness_date",
    "get_graph_store",
    "is_stale",
    "last_business_day",
]
