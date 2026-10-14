"""JSON schema for the Foundation Model API `response_format`.

The endpoint rejects some JSON Schema keywords (it returned 400 "the 'pattern' keyword is
not supported" in the Gate 0 preflight). The model is sent a schema without them, and
every response is still validated locally against the full Pydantic model.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# JSON values as produced by json.loads / model_json_schema.
type Json = dict[str, Any] | list[Any] | str | int | float | bool | None

UNSUPPORTED_KEYWORDS = frozenset(
    {
        "pattern",
        "format",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
    }
)


def strip_unsupported(node: Json, *, is_properties: bool = False) -> Json:
    """Drop unsupported keywords; keys of a `properties` map are field names, kept as is."""
    if isinstance(node, dict):
        return {
            k: strip_unsupported(v, is_properties=(k == "properties" and not is_properties))
            for k, v in node.items()
            if is_properties or k not in UNSUPPORTED_KEYWORDS
        }
    if isinstance(node, list):
        return [strip_unsupported(v) for v in node]
    return node


def wire_schema(model: type[BaseModel]) -> dict[str, Any]:
    return strip_unsupported(model.model_json_schema())
