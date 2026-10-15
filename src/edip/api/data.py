"""Read-only evidence for the live app: snapshots of Delta tables published by the
`gate6_publish` job (each file records its source table, Delta version, and SHA256).

On Databricks the snapshot is copied from the volume at start-up (`EDIP_DATA_VOLUME`);
locally and in tests it is read from `EDIP_DATA_DIR`. The app never computes a number:
every value it shows comes from these files.
"""

from __future__ import annotations

import json
import os
import tempfile
from functools import cached_property
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from edip.workflow.decision import DecisionInputs

TABLES = (
    "cell_annual",
    "cell_stress_results",
    "cell_verdicts",
    "cell_evidence",
    "cell_schedules",
    "cell_excess_months",
    "forecasts",
    "sensitivity_grid",
)
JSON_FILES = ("manifest", "flip_boundary", "capital")
CONFIGS = (
    "agent_allowlist.yaml",
    "acceptance_targets.yaml",
    "battery.yaml",
    "revised_strategy.yaml",
    "model_versions.yaml",
    "stress_tests.yaml",
)

UNITS = {
    "bill_usd": "USD per year, before tax",
    "net_benefit_usd": "USD per year, before tax",
    "kw": "kW (average over the billing interval)",
    "kwh": "kWh",
    "soc_kwh": "kWh",
    "time": "UTC; tariff periods from the Europe/Lisbon wall clock",
}
MEASURED = [
    "actual load (UCI ElectricityLoadDiagrams20112014, client MT_189)",
    "forecasts (pinned model version)",
    "settled bills, peaks, throughput, violations (replay of 2014)",
    "stress test results",
    "agent evaluation scores",
]
ASSUMED = [
    "battery size, efficiency, state of charge window, degradation cost (config/battery.yaml)",
    "operating cost 4,868 USD per year (config/battery.yaml)",
    "stress test parameters (config/stress_tests.yaml)",
    "capital cost, 15 year life, 8 percent discount rate (business case only)",
]


def fetch_volume(volume_dir: str, dest: Path) -> Path:
    """Copy the published snapshot from a Unity Catalog volume (Files API)."""
    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient()
    dest.mkdir(parents=True, exist_ok=True)
    names = [f"{t}.parquet" for t in TABLES] + [f"{j}.json" for j in JSON_FILES]
    names += [f"config/{c}" for c in CONFIGS]
    for name in names:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        resp = ws.files.download(f"{volume_dir.rstrip('/')}/{name}")
        target.write_bytes(resp.contents.read())
    return dest


class AppData:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_env(cls) -> AppData:
        local = os.environ.get("EDIP_DATA_DIR")
        if local:
            return cls(Path(local))
        volume = os.environ.get("EDIP_DATA_VOLUME", "/Volumes/edip/ml/artifacts/app")
        return cls(fetch_volume(volume, Path(tempfile.mkdtemp(prefix="edip_app_data_"))))

    def table(self, name: str) -> pd.DataFrame:
        return self._tables[name]

    @cached_property
    def _tables(self) -> dict[str, pd.DataFrame]:
        return {t: pd.read_parquet(self.root / f"{t}.parquet") for t in TABLES}

    def json(self, name: str) -> Any:  # noqa: ANN401
        return json.loads((self.root / f"{name}.json").read_text())

    def config(self, name: str) -> dict[str, Any]:
        return yaml.safe_load((self.root / "config" / name).read_text())

    @cached_property
    def manifest(self) -> dict[str, Any]:
        return self.json("manifest")

    def provenance(self) -> dict[str, Any]:
        m = self.manifest
        return {
            "mode": "live",
            "result_label": m["result_label"],
            "dataset_sha256": m["dataset_sha256"],
            "model_version": m["model_version"],
            "evaluation_period": m["evaluation_period"],
            "client": m["client"],
            "published_at": m["published_at"],
            "tables": m["tables"],
            "units": UNITS,
            "measured": MEASURED,
            "assumed": ASSUMED,
        }

    def cells(self) -> list[str]:
        v = self.table("cell_verdicts")
        return list(v.sort_values(["power_fraction", "duration_hours"]).cell)

    def decision_inputs(self, cell: str) -> DecisionInputs:
        v = self.table("cell_verdicts")
        row = v[v.cell == cell]
        if row.empty:
            raise KeyError(cell)
        return DecisionInputs.model_validate_json(row.iloc[0].inputs_json)

    def verdict(self, cell: str) -> dict[str, Any]:
        v = self.table("cell_verdicts")
        row = v[v.cell == cell].iloc[0]
        keys = ["frozen_decision", "frozen_reasons", "a1_decision", "a1_reasons", "a1_scope"]
        return {k: row[k] for k in keys} | {"display": row.display, "a1_ref": row.a1_ref}

    def evidence_values(self, cell: str, table: str) -> dict[str, float]:
        e = self.table("cell_evidence")
        e = e[e.cell == cell]
        return {f"{table}|{r.row_key}|{r.column}": float(r.value) for r in e.itertuples()}
