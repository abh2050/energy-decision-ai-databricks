"""Keep the superseded result set (Gate 6 review, owner decision 2026-10-15).

Deep-clones every table produced with the defective guard to <table>_guard_defect and
relabels it "revised strategy, post-hoc (guard defect)". The corrected reruns then
overwrite the original names. Pre-registered tables are untouched.
"""

from __future__ import annotations

import argparse
import json

from edip.core.labels import REVISED_GUARD_DEFECT

TABLES = (
    "curated.dispatch_schedules_revised",
    "curated.settlement_outcomes_revised",
    "curated.replay_outcomes_revised",
    "eval.sensitivity_grid",
    "eval.stress_results",
    "eval.stress_excess_months",
    "eval.stress_peak_moments",
    "eval.decision_verdicts",
    "eval.cell_annual",
    "eval.cell_stress_results",
    "eval.cell_verdicts",
    "eval.cell_evidence",
    "eval.cell_schedules",
    "eval.cell_excess_months",
    "eval.cell_peak_moments",
    "eval.agent_evaluations",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="edip")
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    for t in TABLES:
        src, dst = f"{args.catalog}.{t}", f"{args.catalog}.{t}_guard_defect"
        if spark.catalog.tableExists(dst):
            print(json.dumps({"table": dst, "status": "exists, kept"}))
            continue
        spark.sql(f"CREATE TABLE {dst} DEEP CLONE {src}")
        cols = spark.table(dst).columns
        for col in ("label", "result_label"):
            if col in cols:
                spark.sql(f"UPDATE {dst} SET {col} = '{REVISED_GUARD_DEFECT}'")  # noqa: S608
        spark.sql(
            f"ALTER TABLE {dst} SET TBLPROPERTIES ('edip.result_set' = '{REVISED_GUARD_DEFECT}')"
        )
        print(json.dumps({"table": dst, "rows": spark.table(dst).count()}))
    return 0


if __name__ == "__main__":
    # The Databricks Python task runner reports SystemExit(0) as a failure.
    if code := main():
        raise SystemExit(code)
