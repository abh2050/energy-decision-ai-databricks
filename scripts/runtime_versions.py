"""Record the serverless environment's package versions (no extra dependencies installed).

Run as the bundle job `edip-runtime-probe`; writes runtime_versions.json to the
edip.ml.artifacts volume so job environment pins can match the runtime exactly.
"""

from __future__ import annotations

import importlib.metadata as md
import json
import platform
from pathlib import Path

PACKAGES = ["mlflow", "mlflow-skinny", "protobuf", "pyspark", "pandas", "numpy", "pydantic"]


def main() -> None:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            versions[name] = None
    record = {"python": platform.python_version(), "environment_client": "4", "packages": versions}
    out = Path("/Volumes/edip/ml/artifacts/runtime")
    out.mkdir(parents=True, exist_ok=True)
    (out / "runtime_versions.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
