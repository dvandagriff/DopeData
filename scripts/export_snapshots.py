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

"""Export snapshot data from live sources.

WARNING: This script requires live API credentials for Fivetran and dbt Cloud.
No credentials are configured in this repository — running this script will
print a warning and exit without performing any data export.

To use in production, set the following environment variables:
  - FIVETRAN_API_KEY   : Your Fivetran API key
  - DBT_CLOUD_TOKEN    : Your dbt Cloud personal access token

The exported data is written to ``data/live/`` (create this directory first).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    print("=" * 70)
    print("Dope Live Snapshot Export")
    print("=" * 70)
    print()
    print("WARNING: No live credentials configured.")
    print()
    print("To export data from live sources:")
    print("  1. Create a directory: mkdir -p data/live")
    print("  2. Set environment variables:")
    print("       export FIVETRAN_API_KEY='your-key-here'")
    print("       export DBT_CLOUD_TOKEN='your-token-here'")
    print("  3. Re-run this script")
    print()
    print("Export targets:")
    print("  - data/live/fivetran_connections.json   (from Fivetran API)")
    print("  - data/live/fivetran_schemas.json        (from Fivetran API)")
    print("  - data/live/dbt_manifest.json            (from dbt Cloud API)")
    print("  - data/live/dbt_run_results.json         (from dbt Cloud API)")
    print()
    print("For now, use the snapshot mode (--mode snapshot) which reads")
    print("from static files in data/snapshots/.")
    print("=" * 70)


if __name__ == "__main__":
    main()
