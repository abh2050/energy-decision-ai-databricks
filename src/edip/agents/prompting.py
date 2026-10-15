"""Prompt loading with logged version strings (Gate 5 task 2)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROMPTS = Path(__file__).parent / "prompts"


def load_prompt(name: str, **fields: Any) -> tuple[str, str]:  # noqa: ANN401
    """Return (version, system prompt) for prompts/<name>.md with fields filled in."""
    text = (PROMPTS / f"{name}.md").read_text()
    version = re.search(r"version:\s*([\w.-]+)", text).group(1)
    body = re.sub(r"<!--.*?-->\s*", "", text, count=1, flags=re.S)
    return version, body.format(**{k: json.dumps(v) for k, v in fields.items()})


def user_message(sections: dict[str, Any]) -> str:
    return "\n\n".join(
        f"## {k}\n{json.dumps(v, indent=1, default=str)}" for k, v in sections.items()
    )
