from typing import Literal

from pydantic import BaseModel, Field

from edip.core.wire_schema import UNSUPPORTED_KEYWORDS, wire_schema


class Sample(BaseModel):
    action: Literal["charge", "discharge", "hold"]
    hour: int = Field(ge=0, le=23)
    reason: str = Field(max_length=200)
    # A field literally named like a keyword must survive.
    pattern: str


def _keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from _keys(v)


def test_strips_unsupported_constraint_keywords():
    schema = wire_schema(Sample)
    props = schema["properties"]
    assert "pattern" in props  # field name kept
    for name in ("hour", "reason", "action"):
        assert not UNSUPPORTED_KEYWORDS & set(props[name])


def test_keeps_enum_and_required():
    schema = wire_schema(Sample)
    assert schema["properties"]["action"]["enum"] == ["charge", "discharge", "hold"]
    assert set(schema["required"]) == {"action", "hour", "reason", "pattern"}
