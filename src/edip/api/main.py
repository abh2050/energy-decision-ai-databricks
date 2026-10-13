"""Gate 0 hello world app for Databricks Apps.

Databricks Apps puts an OAuth proxy in front of the app and forwards the signed-in
identity in X-Forwarded-* headers. `/whoami` proves an authenticated request reached
the app. It reports only that the identity headers are present and never echoes or
logs the email or user name (rule 7).
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="EDIP hello", version="0.0.1")


class Health(BaseModel):
    status: str


class WhoAmI(BaseModel):
    authenticated: bool
    user_header_present: bool
    email_header_present: bool


@app.get("/healthz")
def healthz() -> Health:
    return Health(status="ok")


@app.get("/whoami")
def whoami(
    x_forwarded_user: str | None = Header(default=None),
    x_forwarded_email: str | None = Header(default=None),
) -> WhoAmI:
    if not x_forwarded_user and not x_forwarded_email:
        raise HTTPException(status_code=401, detail="no forwarded identity")
    return WhoAmI(
        authenticated=True,
        user_header_present=bool(x_forwarded_user),
        email_header_present=bool(x_forwarded_email),
    )
