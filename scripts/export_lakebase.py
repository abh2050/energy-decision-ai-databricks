"""Export Lakebase operational state before teardown (Gate 7 task 7).

Writes one JSON file per table (scenarios, decision_runs, checkpoints, approvals,
agent_calls). Approvals carry only salted identity hashes; no email is stored anywhere.
Usage: uv run python scripts/export_lakebase.py OUT_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient

from edip.store import lakebase

TABLES = ("scenarios", "decision_runs", "checkpoints", "approvals", "agent_calls")


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    ws = WorkspaceClient(profile="edip")
    with lakebase.connect(ws) as conn, conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"SELECT * FROM edip.{t} ORDER BY created_at")  # noqa: S608 - fixed names
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
            (out / f"{t}.json").write_text(json.dumps(rows, indent=1, default=str))
            print(t, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
