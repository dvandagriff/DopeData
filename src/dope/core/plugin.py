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

"""Plugin infrastructure for pipeline data ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dope.core.graph import GraphStore


class PipelinePlugin(ABC):
    """Base class for pipeline ingestion plugins.

    Subclasses implement :meth:`ingest` to load data from an external source
    (e.g. Fivetran API, dbt manifest files) into a :class:`GraphStore`.
    """

    @abstractmethod
    def ingest(self, store: GraphStore, mode: str = "snapshot", **kwargs: Any) -> int:
        """Ingest data from the source into *store*.

        Parameters
        ----------
        store :
            The graph store to populate.
        mode :
            One of ``"snapshot"`` (full reload) or ``"incremental"`` (diff).
            Defaults to ``"snapshot"``.
        **kwargs :
            Additional source-specific options (credentials, filters, etc.).

        Returns
        -------
        int
            The number of entities (nodes + edges) inserted or updated.
        """
        ...
