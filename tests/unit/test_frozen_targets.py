"""Rule 3: acceptance targets are frozen; any edit to the file fails CI."""

import hashlib
from pathlib import Path

import yaml

TARGETS = Path(__file__).parents[2] / "config" / "acceptance_targets.yaml"
FROZEN_SHA256 = "e8de4951850fd26bf3d0d8183a92562d6ea859f20633fb0608ba27cd3f69843e"


def test_acceptance_targets_unchanged_since_freeze():
    assert hashlib.sha256(TARGETS.read_bytes()).hexdigest() == FROZEN_SHA256


def test_acceptance_targets_status_frozen():
    assert yaml.safe_load(TARGETS.read_text())["status"] == "frozen"
