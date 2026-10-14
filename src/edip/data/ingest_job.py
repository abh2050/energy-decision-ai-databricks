"""Gate 1 Databricks job: snapshot the UCI file, build load_observations, write the report.

Runs on serverless job compute through the bundle (resources/gate1_jobs.yml). Steps:
1. Download the UCI zip into a dated folder of the raw.snapshots volume (FR1), unless that
   snapshot already exists, and record its SHA256, size, source, and attribution.
2. Parse, select the client, fix DST, aggregate, and split (edip.data.pipeline).
3. Overwrite Delta table curated.load_observations with documented columns and units.
4. Write the data quality report next to the snapshot and log it to MLflow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from edip.data.pipeline import build, read_uci

TABLE_COMMENT = (
    "Hourly load for one UCI ElectricityLoadDiagrams20112014 client (Portugal, 2012 to "
    "2014), hours in UTC; tariff periods use the Europe/Lisbon clock. Source: Trindade (2015), UCI "
    "Machine Learning Repository, CC BY 4.0. Built by edip.data.ingest_job (FR1 to FR5)."
)
COLUMN_COMMENTS = {
    "client_id": "UCI client column name, chosen by the selection rule in config/data.yaml",
    "hour_start": "Start of the hour, UTC; 24 hours per day",
    "kw_mean": "Average demand over the hour, kW (mean of four 15 minute average kW readings)",
    "kwh": "Energy in the hour, kWh (sum of 15 minute kW / 4)",
    "n_intervals": "15 minute readings in the hour; always 4",
    "split": "Chronological partition: train, validation, or test",
    "dataset_sha256": "SHA256 of the downloaded UCI zip snapshot",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_hash(cfg: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def snapshot(cfg: dict[str, Any], snapshot_date: str) -> tuple[Path, dict[str, Any]]:
    ds = cfg["dataset"]
    folder = Path(ds["snapshot_volume"]) / "uci_ld2011_2014" / snapshot_date
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(ds["source_url"]).name
    manifest_path = folder / "manifest.json"
    retrieval = "uploaded via the Files API from a local download of source_url"
    if not target.exists():
        # Serverless egress may be blocked by the workspace network policy; then upload
        # the file first (see docs/setup/workspace.md) and this branch is skipped.
        retrieval = "downloaded by the job from source_url"
        with (
            urllib.request.urlopen(ds["source_url"], timeout=600) as resp,  # noqa: S310
            target.open("wb") as fh,
        ):
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
    manifest = {
        "source_url": ds["source_url"],
        "doi": ds["doi"],
        "license": ds["license"],
        "attribution": ds["attribution"],
        "file": target.name,
        "bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "snapshot_date": snapshot_date,
        "retrieval": retrieval,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return target, manifest


def write_delta(spark: Any, pdf: Any, table: str, cfg_hash: str, sha: str) -> None:  # noqa: ANN401
    df = spark.createDataFrame(pdf)
    (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table))
    spark.sql(f"COMMENT ON TABLE {table} IS '{TABLE_COMMENT}'")
    for col, text in COLUMN_COMMENTS.items():
        spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} COMMENT '{text}'")
    spark.sql(
        f"ALTER TABLE {table} SET TBLPROPERTIES ("
        f"'edip.dataset_sha256' = '{sha}', 'edip.config_hash' = '{cfg_hash}', "
        "'edip.units' = 'kW, kWh', 'edip.timezone' = 'UTC')"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/data.yaml")
    parser.add_argument("--snapshot-date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--catalog", default="edip")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    cfg_hash = config_hash(cfg)
    zip_path, manifest = snapshot(cfg, args.snapshot_date)

    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path) as zf:
        member = zf.extract(cfg["dataset"]["member"], tmp)
        wide = read_uci(member)
    table_pdf, report = build(wide, cfg, manifest["sha256"])

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    table = f"{args.catalog}.curated.load_observations"
    write_delta(spark, table_pdf, table, cfg_hash, manifest["sha256"])
    version = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]["version"]

    result = {
        "manifest": manifest,
        "config_hash": cfg_hash,
        "table": table,
        "delta_version": int(version),
        "report": report.model_dump(mode="json"),
    }
    report_path = zip_path.parent / "gate1_data_quality.json"
    report_path.write_text(json.dumps(result, indent=2) + "\n")

    import mlflow

    mlflow.set_experiment("/Shared/edip/gate1_data")
    with mlflow.start_run(run_name="gate1-ingest"):
        mlflow.set_tags(
            {"gate": "1", "dataset_sha256": manifest["sha256"], "config_hash": cfg_hash}
        )
        mlflow.log_params(
            {"client_id": report.selection.client_id, "table": table, "delta_version": version}
        )
        mlflow.log_metrics(
            {f"hours_{s.name}": s.hours for s in report.splits}
            | {"candidates": len(report.selection.candidates)}
        )
        mlflow.log_dict(result, "gate1_data_quality.json")
    print(json.dumps({"client": report.selection.client_id, "rows": report.hourly_rows}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
