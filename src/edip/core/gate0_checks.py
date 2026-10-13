"""Pure Gate 0 exit check: turns an observed resource snapshot into pass/fail items."""

from __future__ import annotations

from pydantic import BaseModel

REQUIRED_SCHEMAS = frozenset({"raw", "curated", "ml", "eval"})
REQUIRED_LAKEBASE_TABLES = frozenset(
    {"scenarios", "decision_runs", "checkpoints", "approvals", "agent_calls"}
)


class Gate0Snapshot(BaseModel):
    """What the verifier observed. Names and states only; no IDs, hosts, or users."""

    catalog_exists: bool
    schemas: set[str]
    storage_credential_exists: bool
    external_location_exists: bool
    lakebase_instance_exists: bool
    lakebase_tables: set[str]
    app_exists: bool
    app_deployed: bool
    warehouse_auto_stop_mins: dict[str, int | None]
    max_auto_stop_mins: int


class CheckItem(BaseModel):
    name: str
    passed: bool
    detail: str = ""


def evaluate(s: Gate0Snapshot) -> list[CheckItem]:
    missing_schemas = sorted(REQUIRED_SCHEMAS - s.schemas)
    missing_tables = sorted(REQUIRED_LAKEBASE_TABLES - s.lakebase_tables)
    bad_warehouses = sorted(
        name
        for name, mins in s.warehouse_auto_stop_mins.items()
        if mins is None or mins <= 0 or mins > s.max_auto_stop_mins
    )
    return [
        CheckItem(name="catalog edip", passed=s.catalog_exists),
        CheckItem(
            name="schemas raw/curated/ml/eval",
            passed=not missing_schemas,
            detail=f"missing {missing_schemas}" if missing_schemas else "",
        ),
        CheckItem(name="storage credential", passed=s.storage_credential_exists),
        CheckItem(name="external location", passed=s.external_location_exists),
        CheckItem(name="lakebase instance", passed=s.lakebase_instance_exists),
        CheckItem(
            name="lakebase tables",
            passed=s.lakebase_instance_exists and not missing_tables,
            detail=f"missing {missing_tables}" if missing_tables else "",
        ),
        CheckItem(name="app deployed", passed=s.app_exists and s.app_deployed),
        CheckItem(
            name="warehouse auto stop",
            passed=not bad_warehouses,
            detail=f"not set: {bad_warehouses}" if bad_warehouses else "",
        ),
    ]
