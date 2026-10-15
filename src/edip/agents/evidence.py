"""Evidence store and response validation (FR25, Gate 5 task 7).

Agents only see an evidence packet built from persisted values. The validator rejects any
response that cites a row not in the packet, states a number that does not match the cited
value, or (planning) proposes a change outside the allowlist or to a hard constraint.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from edip.agents.schemas import (
    BusinessResponse,
    Claim,
    Comparison,
    EvidenceRef,
    PlanningResponse,
    RiskResponse,
)

NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")
# Words that compare values. A plain claim using one is rejected: comparisons must be
# typed (Comparison) so the validator can check them (Gate 6 review, 2026-10-15).
COMPARATIVE = re.compile(
    r"\b(higher|lower|greater|smaller|larger|bigger|more than|less than|fewer than|"
    r"exceeds?|exceeded|outperforms?|underperforms?|better|worse|cheaper|costlier|"
    r"beats?|surpass(es)?)\b",
    re.I,
)
# Reasons with this prefix are format violations (the claim may be true but is not in
# the checkable form). They are rejected like any other reason; evaluation reports them
# separately as format compliance.
FORMAT = "format: "


def is_format(reason: str) -> bool:
    return reason.startswith(FORMAT)


OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: _close(a, b),
    "!=": lambda a, b: not _close(a, b),
}


def key(ref: EvidenceRef) -> str:
    return f"{ref.table}|{ref.row_key}|{ref.column}"


class EvidencePacket(BaseModel):
    """Persisted values an agent may cite, keyed by table|row_key|column."""

    values: dict[str, float | str]

    def get(self, ref: EvidenceRef) -> float | str | None:
        return self.values.get(key(ref))

    def as_prompt_rows(self) -> list[dict[str, Any]]:
        rows = []
        for k, v in self.values.items():
            table, row_key, column = k.split("|", 2)
            rows.append({"table": table, "row_key": row_key, "column": column, "value": v})
        return rows


def _numbers(text: str) -> list[float]:
    out = []
    for m in NUMBER.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def _close(a: float, b: float, rel: float = 0.005, abs_tol: float = 0.5) -> bool:
    return abs(a - b) <= max(abs_tol, rel * abs(b))


def check_claims(claims: list[Claim], packet: EvidencePacket) -> list[str]:
    """Reasons a set of claims is unsupported (empty when every claim checks out)."""
    reasons = []
    cited = [packet.get(c.evidence_ref) for c in claims]
    numeric = [float(v) for v in cited if isinstance(v, int | float)]
    for claim, value in zip(claims, cited, strict=True):
        if value is None:
            reasons.append(f"cites a row not in the evidence packet: {key(claim.evidence_ref)}")
            continue
        if COMPARATIVE.search(claim.text):
            reasons.append(
                f"{FORMAT}untyped comparison in a claim (use a typed comparison): {claim.text[:80]}"
            )
        if claim.value is not None and (
            not isinstance(value, int | float) or not _close(claim.value, float(value))
        ):
            reasons.append(f"value {claim.value} does not match {key(claim.evidence_ref)}")
        # Every number written in the text must match some cited value (small integers
        # such as years, months, or counts of 1 to 31 are allowed as plain language).
        for n in _numbers(claim.text):
            if abs(n) <= 31 or n in (2012, 2013, 2014, 2026):
                continue
            if not any(_close(n, v) or _close(abs(n), abs(v)) for v in numeric):
                reasons.append(f"number {n:g} in claim text is not in the cited evidence")
    return reasons


def check_comparisons(comparisons: list[Comparison], packet: EvidencePacket) -> list[str]:
    """Reasons a set of typed comparisons is unsupported or false."""
    reasons = []
    for c in comparisons:
        left = packet.get(c.left)
        if c.right is not None:
            right = packet.get(c.right)
            rname = key(c.right)
        else:
            right, rname = c.right_value, "constant"
        if not isinstance(left, int | float):
            reasons.append(f"comparison cites a row not in the evidence packet: {key(c.left)}")
            continue
        if not isinstance(right, int | float):
            reasons.append(f"comparison has no valid right-hand value ({rname})")
            continue
        if not OPS[c.operator](float(left), float(right)):
            reasons.append(
                f"false comparison: {key(c.left)} = {float(left):g} is not "
                f"{c.operator} {rname} = {float(right):g}"
            )
        for n in _numbers(c.text):
            if abs(n) <= 31 or n in (2012, 2013, 2014, 2026):
                continue
            if not any(_close(n, v) or _close(abs(n), abs(v)) for v in (left, right)):
                reasons.append(f"number {n:g} in comparison text is not in the cited evidence")
    return reasons


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def check_quotes(
    resp: PlanningResponse, request: str, keyword_map: dict[str, list[str]]
) -> list[str]:
    """Planning v3: each change quotes the operator request, and the quote names the field
    through the keyword map (config/planning_keywords.yaml)."""
    reasons = []
    req = _norm(request)
    for change in resp.changes:
        quote = _norm(change.quote)
        if change.field not in keyword_map:
            reasons.append(f"field {change.field} is outside the keyword map")
            continue
        if not quote or quote not in req:
            reasons.append(f"quote for {change.field} is missing from the operator request")
            continue
        words = [w.lower() for w in keyword_map[change.field]]
        if not any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", quote) for w in words):
            reasons.append(f"quote for {change.field} does not name that field")
    return reasons


def check_planning(
    resp: PlanningResponse,
    allowlist: dict[str, Any],
    packet: EvidencePacket,
    request: str | None = None,
    keyword_map: dict[str, list[str]] | None = None,
) -> list[str]:
    """`request` and `keyword_map` (planning v3) turn on the quote check."""
    cfg = allowlist["planning_agent"]
    allowed: dict[str, list[Any]] = cfg["allowed_fields"]
    reasons = []
    for change in resp.changes:
        if change.field in cfg["hard_constraints"]:
            reasons.append(f"proposes a change to hard constraint {change.field}")
        elif change.field not in allowed:
            reasons.append(f"field {change.field} is not on the allowlist")
        elif change.new_value not in allowed[change.field] and str(change.new_value) not in [
            str(v) for v in allowed[change.field]
        ]:
            reasons.append(f"value {change.new_value} is not allowed for {change.field}")
    if request is not None and keyword_map is not None:
        reasons += check_quotes(resp, request, keyword_map)
    return reasons + check_claims(resp.claims, packet) + check_comparisons(resp.comparisons, packet)


def check_risk(resp: RiskResponse, allowlist: dict[str, Any], packet: EvidencePacket) -> list[str]:
    allowed = allowlist["risk_agent"]["allowed_stress_tests"]
    reasons = [f"stress test {t} is not allowed" for t in resp.selection.tests if t not in allowed]
    return (
        reasons + check_claims(resp.findings, packet) + check_comparisons(resp.comparisons, packet)
    )


def check_business(
    resp: BusinessResponse,
    allowlist: dict[str, Any],
    packet: EvidencePacket,
    required_decision: str | None = None,
) -> list[str]:
    """`required_decision` (business prompt v3): the deterministic A1 verdict; a response
    that recommends anything else is rejected."""
    reasons = []
    if required_decision is not None and resp.decision != required_decision:
        reasons.append(
            f"recommendation {resp.decision} differs from the A1 verdict {required_decision}"
        )
    if resp.decision not in allowlist["business_agent"]["allowed_decisions"]:
        reasons.append(f"decision {resp.decision} is not allowed")
    if re.search(r"\b(i|we) (approve|have approved)\b", resp.rationale, re.I):
        reasons.append("the business agent may not approve; only the operator approves")
    return reasons + check_claims(resp.claims, packet) + check_comparisons(resp.comparisons, packet)
