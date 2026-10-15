"""Export the live app's read-only responses as static JSON for the public pages (Gate 7).

Runs the real FastAPI app on the published snapshot (Delta-derived, with manifest) and
saves what each view endpoint returns, so the public pages show exactly what the live
app showed. No model calls, no store writes.

Usage: EDIP_DATA_DIR=SNAPSHOT_DIR uv run python scripts/export_public.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from edip.api.data import AppData
from edip.api.main import NullModel, create_app
from edip.store.repo import MemoryRepo
from edip.workflow.decision import DecisionInputs, decide
from edip.workflow.run import cell_key

OUT = Path("frontend/public/data/replay")


def write_trace_index() -> None:
    """Index of the recorded traces with the deterministic verdicts for the battery cell
    each run actually evaluated (scenario evidence is scripted for evaluation)."""
    traces = Path("frontend/public/data/traces")
    index = []
    for path in sorted(traces.glob("[sh]*.json")):
        t = json.loads(path.read_text())
        sc = yaml.safe_load((Path("evals/scenarios") / f"{t['scenario_id']}.yaml").read_text())
        cells = {k: DecisionInputs.model_validate(v) for k, v in sc["cells"].items()}
        cell = cell_key(t["applied_settings"])
        r = decide(cells.get(cell, cells[cell_key(sc["current_settings"])]))
        index.append(
            {
                "scenario_id": t["scenario_id"],
                "title": t["title"],
                "split": "held_out" if t["scenario_id"].startswith("h") else "development",
                "operator_objective": t["operator_objective"],
                "operator_concerns": sc.get("operator_concerns", ""),
                "operator_confirms": sc.get("operator_confirms", True),
                "current_settings": sc["current_settings"],
                "evidence": "scripted for evaluation",
                "verdicts": {
                    "frozen_decision": r.frozen_decision,
                    "frozen_reasons": "; ".join(r.frozen_reasons),
                    "a1_decision": r.decision,
                    "a1_reasons": "; ".join(r.reasons),
                    "a1_scope": "; ".join(f"{a}/{b}" for a, b in r.scope),
                    "display": r.display,
                    "a1_ref": r.a1_ref,
                },
            }
        )
    (traces / "index.json").write_text(json.dumps(index, indent=1))


def main() -> int:
    data = AppData(Path(os.environ["EDIP_DATA_DIR"]))
    client = TestClient(create_app(data, MemoryRepo(), lambda: NullModel()))
    h = {"X-Forwarded-Email": "public@example.com"}
    OUT.mkdir(parents=True, exist_ok=True)

    def save(name: str, path: str) -> dict:
        r = client.get(path, headers=h)
        r.raise_for_status()
        body = r.json()
        (OUT / f"{name}.json").write_text(json.dumps(body, separators=(",", ":")))
        return body

    meta = save("meta", "/api/meta")
    save("sensitivity", "/api/sensitivity")
    for cell in meta["cells"]:
        key = cell.replace("/", "_")
        save(f"strategies_{key}", f"/api/strategies?cell={cell}")
        save(f"business_{key}", f"/api/business-case?cell={cell}")
    (OUT / "manifest.json").write_text(json.dumps(data.manifest, indent=1))
    write_trace_index()
    print(sorted(p.name for p in OUT.glob("*.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
