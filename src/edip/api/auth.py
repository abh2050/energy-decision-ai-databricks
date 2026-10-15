"""Identity and roles, enforced on the server (PRD 4.1).

Databricks Apps signs users in with OAuth and forwards the identity in X-Forwarded-*
headers. A request without them is rejected. The operator role is granted to identities
whose salted SHA256 hash is listed in `EDIP_OPERATOR_HASHES` (set from a secret scope, so
no email is ever in the repository, rule 7); everyone else signed in is a viewer.
Only the hash is stored with an approval.
"""

from __future__ import annotations

import hashlib
import os
from typing import Literal

from fastapi import Depends, Header, HTTPException
from pydantic import BaseModel

Role = Literal["operator", "viewer"]


def identity_hash(identity: str, salt: str | None = None) -> str:
    salt = os.environ.get("EDIP_IDENTITY_SALT", "edip") if salt is None else salt
    return hashlib.sha256(f"{salt}:{identity.strip().lower()}".encode()).hexdigest()


class User(BaseModel):
    identity_hash: str
    role: Role


def operator_hashes() -> set[str]:
    raw = os.environ.get("EDIP_OPERATOR_HASHES", "")
    return {h.strip() for h in raw.split(",") if h.strip()}


def current_user(
    x_forwarded_email: str | None = Header(default=None),
    x_forwarded_user: str | None = Header(default=None),
    x_forwarded_preferred_username: str | None = Header(default=None),
) -> User:
    identity = x_forwarded_email or x_forwarded_preferred_username or x_forwarded_user
    if not identity:
        raise HTTPException(status_code=401, detail="sign in required")
    h = identity_hash(identity)
    return User(identity_hash=h, role="operator" if h in operator_hashes() else "viewer")


def require_operator(user: User = Depends(current_user)) -> User:  # noqa: B008
    if user.role != "operator":
        raise HTTPException(status_code=403, detail="operator role required")
    return user
