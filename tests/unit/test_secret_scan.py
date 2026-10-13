import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "scan_public_bundle", Path(__file__).parents[2] / "scripts/scan_public_bundle.py"
)
scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scan)

# Fake secrets are assembled at runtime so this file does not trip the scanner itself.
FAKE_TOKEN = "dapi" + "0" * 32
FAKE_AWS = "AKIA" + "A" * 16
FAKE_HOST = "dbc-1234abcd" + ".cloud.databricks.com"
FAKE_EMAIL = "person" + "@" + "corp.io"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (f"host = https://{FAKE_HOST}", "databricks_workspace_url"),
        (f"token={FAKE_TOKEN}", "databricks_token"),
        (f"key {FAKE_AWS}", "aws_access_key"),
        (f"contact {FAKE_EMAIL}", "email"),
    ],
    ids=["url", "token", "aws", "email"],
)
def test_detects(text, kind):
    assert [f.kind for f in scan.scan_text(text)] == [kind]


def test_allows_placeholder_email_and_clean_text():
    assert scan.scan_text("mail someone@example.com about the tariff") == []
    assert scan.scan_text("battery charges at 50 kW") == []
    assert scan.scan_text("--host https://accounts.cloud.databricks.com") == []


def test_scan_paths_and_skip_dirs(tmp_path):
    (tmp_path / "ok.txt").write_text("nothing here")
    (tmp_path / "bad.js").write_text(f"const t = '{FAKE_TOKEN}';")
    skipped = tmp_path / "node_modules"
    skipped.mkdir()
    (skipped / "x.js").write_text(f"'{FAKE_TOKEN}'")
    findings = scan.scan_paths([tmp_path])
    assert [(Path(f.path).name, f.kind) for f in findings] == [("bad.js", "databricks_token")]


def test_main_exit_codes(tmp_path):
    (tmp_path / "a.txt").write_text("clean")
    assert scan.main([str(tmp_path)]) == 0
    (tmp_path / "b.txt").write_text(FAKE_EMAIL)
    assert scan.main([str(tmp_path)]) == 1
