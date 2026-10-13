"""Fail if files contain a Databricks workspace URL, a token pattern, or an email address.

Used in CI on the whole repo now and on the public Pages bundles at Gate 7 (rule 7).
Usage: uv run python scripts/scan_public_bundle.py PATH [PATH ...]
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import BaseModel

PATTERNS: dict[str, re.Pattern[str]] = {
    "databricks_workspace_url": re.compile(
        r"[a-z0-9-]+\.(?:cloud\.databricks\.com|databricksapps\.com|"
        r"azuredatabricks\.net|gcp\.databricks\.com)",
        re.I,
    ),
    "databricks_token": re.compile(r"\bdapi[0-9a-f]{32}\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}
# Placeholder domains that are safe in docs and tests.
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
# Shared Databricks hosts that identify no workspace.
ALLOWED_HOSTS = {"accounts.cloud.databricks.com"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".databricks",
    ".ruff_cache",
    ".pytest_cache",
}
SKIP_FILES = {"uv.lock", "package-lock.json"}


class Finding(BaseModel):
    path: str
    line: int
    kind: str


def _allowed(kind: str, match: str) -> bool:
    if kind == "email":
        domain = match.rsplit("@", 1)[1].lower()
        return domain in ALLOWED_EMAIL_DOMAINS
    if kind == "databricks_workspace_url":
        return match.lower() in ALLOWED_HOSTS
    return False


def scan_text(text: str, path: str = "<text>") -> list[Finding]:
    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS.items():
            for m in pattern.finditer(line):
                if not _allowed(kind, m.group(0)):
                    findings.append(Finding(path=path, line=lineno, kind=kind))
    return findings


def iter_files(paths: Iterable[Path]) -> Iterator[Path]:
    for root in paths:
        if root.is_file():
            yield root
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and not SKIP_DIRS.intersection(p.parts) and p.name not in SKIP_FILES:
                yield p


def scan_paths(paths: Iterable[Path]) -> list[Finding]:
    findings = []
    for p in iter_files(paths):
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(text, str(p)))
    return findings


def main(argv: list[str]) -> int:
    findings = scan_paths([Path(a) for a in argv] or [Path()])
    for f in findings:
        # Print location and kind only, never the matched secret.
        print(f"{f.path}:{f.line}: {f.kind}")
    print(f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
