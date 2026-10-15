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
    EvidenceRef,
    PlanningResponse,
    RiskResponse,
)

NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


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


def check_planning(
    resp: PlanningResponse, allowlist: dict[str, Any], packet: EvidencePacket
) -> list[str]:
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
    return reasons + check_claims(resp.claims, packet)


def check_risk(resp: RiskResponse, allowlist: dict[str, Any], packet: EvidencePacket) -> list[str]:
    allowed = allowlist["risk_agent"]["allowed_stress_tests"]
    reasons = [f"stress test {t} is not allowed" for t in resp.selection.tests if t not in allowed]
    return reasons + check_claims(resp.findings, packet)


def check_business(
    resp: BusinessResponse, allowlist: dict[str, Any], packet: EvidencePacket
) -> list[str]:
    reasons = []
    if resp.decision not in allowlist["business_agent"]["allowed_decisions"]:
        reasons.append(f"decision {resp.decision} is not allowed")
    if re.search(r"\b(i|we) (approve|have approved)\b", resp.rationale, re.I):
        reasons.append("the business agent may not approve; only the operator approves")
    return reasons + check_claims(resp.claims, packet)
