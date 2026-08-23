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

from __future__ import annotations

from enum import Enum
from typing import Literal


class NodeType(Enum):
    FIVETRAN_CONNECTION = "FivetranConnection"
    SNOWFLAKE_TABLE = "SnowflakeTable"
    DBT_MODEL = "dbtModel"
    DBT_TEST = "dbtTest"
    DBT_SOURCE = "dbtSource"
    DATA_PRODUCT = "DataProduct"


EdgeType = Literal[
    "SYNC_TO",
    "PRODUCES",
    "DEPENDS_ON",
    "TESTS",
    "FEEDS",
    "EXPOSED_BY",
]


def _normalize_type(value: NodeType | str) -> str:
    """Return the string value for a node type (enum or literal)."""
    if isinstance(value, NodeType):
        return value.value
    return str(value)


CYPHER_DDL: str = """\
CREATE NODE TABLE FivetranConnection(
    id STRING PRIMARY KEY,
    source_id STRING,
    name STRING,
    status STRING,
    synced_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
) UNIQUE (id);

CREATE NODE TABLE SnowflakeTable(
    id STRING PRIMARY KEY,
    database STRING,
    schema_name STRING,
    table_name STRING,
    row_count INT64,
    size_bytes INT64,
    last_analyzed TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
) UNIQUE (id);

CREATE NODE TABLE dbtModel(
    id STRING PRIMARY KEY,
    package_name STRING,
    name STRING,
    type STRING,
    materialization STRING,
    database STRING,
    schema_name STRING,
    table_name STRING,
    updated_at TIMESTAMP
) UNIQUE (id);

CREATE NODE TABLE dbtTest(
    id STRING PRIMARY KEY,
    model_id STRING,
    name STRING,
    type STRING,
    status STRING,
    run_duration_ms FLOAT64,
    executed_at TIMESTAMP
) UNIQUE (id);

CREATE NODE TABLE dbtSource(
    id STRING PRIMARY KEY,
    package_name STRING,
    name STRING,
    database STRING,
    schema_name STRING,
    table_name STRING,
    loaded_at TIMESTAMP
) UNIQUE (id);

CREATE NODE TABLE DataProduct(
    id STRING PRIMARY KEY,
    name STRING,
    description STRING,
    owner STRING,
    team STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
) UNIQUE (id);

CREATE REL TABLE SYNC_TO(
    FROM FivetranConnection TO SnowflakeTable
) FULL；

CREATE REL TABLE PRODUCES(
    FROM dbtModel OR dbtSource TO SnowflakeTable
) FULL;

CREATE REL TABLE DEPENDS_ON(
    FROM dbtModel TO dbtModel
) FULL;

CREATE REL TABLE TESTS(
    FROM dbtTest TO dbtModel
) FULL;

CREATE REL TABLE FEEDS(
    FROM SnowflakeTable TO DataProduct
) FULL;

CREATE REL TABLE EXPOSED_BY(
    FROM DataProduct TO dbtModel
) FULL;\
"""
