from edip.core.gate0_checks import Gate0Snapshot, evaluate


def _snapshot(**overrides):
    base = dict(
        catalog_exists=True,
        schemas={"raw", "curated", "ml", "eval", "default"},
        storage_credential_exists=True,
        external_location_exists=True,
        lakebase_instance_exists=True,
        lakebase_tables={"scenarios", "decision_runs", "checkpoints", "approvals", "agent_calls"},
        app_exists=True,
        app_deployed=True,
        warehouse_auto_stop_mins={"starter": 5},
        max_auto_stop_mins=10,
    )
    base.update(overrides)
    return Gate0Snapshot(**base)


def _failed(snapshot):
    return [c.name for c in evaluate(snapshot) if not c.passed]


def test_all_present_passes():
    assert _failed(_snapshot()) == []


def test_missing_schema_fails():
    assert _failed(_snapshot(schemas={"raw", "ml"})) == ["schemas raw/curated/ml/eval"]


def test_warehouse_without_auto_stop_fails():
    assert _failed(_snapshot(warehouse_auto_stop_mins={"a": 5, "b": 0})) == ["warehouse auto stop"]


def test_missing_lakebase_instance_fails_tables_too():
    assert _failed(_snapshot(lakebase_instance_exists=False, lakebase_tables=set())) == [
        "lakebase instance",
        "lakebase tables",
    ]


def test_app_not_deployed_fails():
    assert _failed(_snapshot(app_deployed=False)) == ["app deployed"]
