import re
from pathlib import Path

from edip.store.models import TABLE_MODELS

DDL = (Path(__file__).parents[2] / "src/edip/store/lakebase_schema.sql").read_text()
REQUIRED_TABLES = {"scenarios", "decision_runs", "checkpoints", "approvals", "agent_calls"}
NON_COLUMN_WORDS = {"UNIQUE", "PRIMARY", "CONSTRAINT", "CHECK", "FOREIGN"}


def ddl_columns(table: str) -> list[str]:
    body = re.search(rf"CREATE TABLE IF NOT EXISTS edip\.{table} \((.*?)\n\);", DDL, re.S).group(1)
    cols = []
    for line in body.splitlines():
        m = re.match(r"\s{4}([a-z_]+)\s+[A-Z]", line)
        if m and m.group(1).upper() not in NON_COLUMN_WORDS:
            cols.append(m.group(1))
    return cols


def test_all_required_tables_have_models():
    assert set(TABLE_MODELS) == REQUIRED_TABLES


def test_ddl_columns_match_models():
    for table, model in TABLE_MODELS.items():
        assert ddl_columns(table) == list(model.model_fields), table


def test_decision_runs_carry_lineage():
    cols = set(ddl_columns("decision_runs"))
    assert {
        "dataset_hash",
        "model_version",
        "tariff_hash",
        "battery_hash",
        "optimizer_settings",
        "prompt_versions",
        "mlflow_run_id",
        "mlflow_trace_ids",
    } <= cols
