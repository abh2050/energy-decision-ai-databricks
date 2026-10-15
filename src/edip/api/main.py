"""EDIP live app (Gate 6): FastAPI backend and the built React app, on Databricks Apps.

Every response that carries numbers also carries provenance (source Delta table and
version, result label, evaluation period, units, and measured versus assumed lists).
Roles are enforced here, not in the browser: viewers can read everything; only operators
can create scenarios, start runs, confirm plans, and approve, revise, or reject.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from edip.agents.llm import ModelClient
from edip.api.auth import User, current_user, require_operator
from edip.api.data import AppData
from edip.store.repo import Repo
from edip.workflow.live import LiveWorkflow, WorkflowError

STATIC = Path(__file__).parent / "static"
ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


class Health(BaseModel):
    status: str


class WhoAmI(BaseModel):
    authenticated: bool
    role: str


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tariff_id: str
    strategy: str
    power_fraction: float
    duration_hours: int


class RunIn(BaseModel):
    scenario_id: str
    objective: str = Field(min_length=1, max_length=1000)
    concerns: str = Field(default="", max_length=1000)


class ConfirmIn(BaseModel):
    confirmed: bool


class DecisionIn(BaseModel):
    decision: Literal["approve", "revise", "reject"]
    comment: str | None = Field(default=None, max_length=1000)


class NullModel:
    """No model endpoint (tests, offline): every agent call falls back to its template."""

    def complete(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        raise RuntimeError("model endpoint disabled (EDIP_MODEL=none)")


def default_client_factory() -> Callable[[], ModelClient]:
    if os.environ.get("EDIP_MODEL", "fmapi") == "none":
        return NullModel
    from edip.agents.llm import DatabricksModel

    timeout = float(os.environ.get("EDIP_MODEL_TIMEOUT_S", "40"))
    model = DatabricksModel(ENDPOINT, timeout)  # one client; calls stay spaced 2 s apart
    return lambda: model


def default_repo() -> Repo:
    if os.environ.get("EDIP_STORE", "lakebase") == "memory":
        from edip.store.repo import MemoryRepo

        return MemoryRepo()
    from edip.store.repo import LakebaseRepo

    return LakebaseRepo()


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.astype(object).where(df.notna(), None).to_dict("records")


def create_app(
    data: AppData | None = None,
    repo: Repo | None = None,
    client_factory: Callable[[], ModelClient] | None = None,
) -> FastAPI:
    app = FastAPI(title="EDIP", version="1.0.0")
    state: dict[str, Any] = {}

    def wf() -> LiveWorkflow:
        if "wf" not in state:
            d = data or AppData.from_env()
            state["wf"] = LiveWorkflow(
                d, repo or default_repo(), client_factory or default_client_factory(), ENDPOINT
            )
        return state["wf"]

    def conflict(fn: Callable[[], Any]) -> Any:  # noqa: ANN401
        try:
            return fn()
        except WorkflowError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"not found: {e}") from e

    @app.get("/healthz")
    def healthz() -> Health:
        return Health(status="ok")

    @app.get("/whoami")
    def whoami(user: User = Depends(current_user)) -> WhoAmI:  # noqa: B008
        return WhoAmI(authenticated=True, role=user.role)

    @app.get("/api/meta")
    def meta(user: User = Depends(current_user)) -> dict[str, Any]:  # noqa: B008
        d = wf().data
        allow = d.config("agent_allowlist.yaml")["planning_agent"]["allowed_fields"]
        return {
            "role": user.role,
            "provenance": d.provenance(),
            "cells": d.cells(),
            "allowed_fields": allow,
            "base_cell": "0.5/2",
        }

    @app.get("/api/strategies")
    def strategies(
        cell: str = Query("0.5/2"),
        user: User = Depends(current_user),  # noqa: B008
    ) -> dict[str, Any]:
        d = wf().data
        a = d.table("cell_annual")
        a = a[a.cell == cell]
        if a.empty:
            raise HTTPException(404, f"no results for cell {cell}")
        inputs = d.decision_inputs(cell)
        target = {(s.tariff_id, s.strategy): s.passes_target for s in inputs.strategies}
        rows = []
        for r in a.itertuples():
            rows.append(
                {
                    "tariff_id": r.tariff_id,
                    "strategy": r.strategy,
                    "bill_usd": r.bill_usd,
                    "net_benefit_usd": r.net_benefit_usd,
                    "max_billing_demand_kw": r.max_billing_demand_kw,
                    "peak_grid_kw": r.peak_grid_kw,
                    "throughput_kwh": r.throughput_kwh,
                    "degradation_usd": r.degradation_usd,
                    "regret_vs_hindsight_usd": r.regret_vs_hindsight_usd,
                    "violations": int(r.violations),
                    "passes_frozen_target": target.get((r.tariff_id, r.strategy)),
                }
            )
        return {
            "cell": cell,
            "rows": rows,
            "source": d.manifest["tables"]["cell_annual"],
            "label": d.manifest["result_label"],
        }

    @app.get("/api/operating")
    def operating(
        cell: str = Query("0.5/2"),
        tariff_id: str = Query("pge_b19_secondary"),
        strategy: str = Query("robust_quantile"),
        day: str | None = Query(None),
        user: User = Depends(current_user),  # noqa: B008
    ) -> dict[str, Any]:
        d = wf().data
        s = d.table("cell_schedules")
        s = s[(s.cell == cell) & (s.tariff_id == tariff_id) & (s.strategy == strategy)]
        if s.empty:
            raise HTTPException(404, "no schedule for that cell, tariff and strategy")
        hours = pd.to_datetime(s.hour_start)
        days = sorted({h.strftime("%Y-%m-%d") for h in hours})
        day = day or days[-1]
        if day not in days:
            raise HTTPException(404, f"day {day} not in the evaluation period")
        sday = s[hours.dt.strftime("%Y-%m-%d") == day].copy()
        f = d.table("forecasts")
        fh = pd.to_datetime(f.target_hour)
        fday = f[fh.dt.strftime("%Y-%m-%d") == day]
        cols = ["actual", "point", "p10", "p50", "p90"]
        fmap = {str(pd.Timestamp(r.target_hour)): r for r in fday.itertuples()}
        rows = []
        for r in sday.itertuples():
            fr = fmap.get(str(pd.Timestamp(r.hour_start)))
            rows.append(
                {
                    "hour_start_utc": str(pd.Timestamp(r.hour_start)),
                    **{c: (getattr(fr, c) if fr is not None else None) for c in cols},
                    "planned_charge_kw": r.planned_charge_kw,
                    "planned_discharge_kw": r.planned_discharge_kw,
                    "charge_kw": r.charge_kw,
                    "discharge_kw": r.discharge_kw,
                    "soc_kwh": r.soc_kwh,
                    "grid_kw": r.grid_kw,
                    "guard_clipped_kw": r.guard_clipped_kw,
                }
            )
        return {
            "cell": cell,
            "tariff_id": tariff_id,
            "strategy": strategy,
            "day": day,
            "days": days,
            "rows": rows,
            "sources": {
                "forecasts": d.manifest["tables"]["forecasts"],
                "schedule": d.manifest["tables"]["cell_schedules"],
            },
            "label": d.manifest["result_label"],
        }

    @app.get("/api/sensitivity")
    def sensitivity(user: User = Depends(current_user)) -> dict[str, Any]:  # noqa: B008
        d = wf().data
        g = d.table("sensitivity_grid")
        base = g[
            (g.round_trip_efficiency.round(2) == 0.90)
            & (g.degradation_usd_per_kwh.round(3) == 0.03)
            & (g.demand_charge_multiplier.round(2) == 1.0)
        ]
        cols = [
            "tariff_id",
            "spread_multiplier",
            "power_fraction",
            "duration_hours",
            "strategy",
            "net_benefit_usd",
            "beats_no_battery",
            "beats_fixed",
        ]
        return {
            "flip_boundary": d.json("flip_boundary"),
            "base_cost_cells": _records(base[cols]),
            "source": d.manifest["tables"]["sensitivity_grid"],
            "label": d.manifest["result_label"],
        }

    @app.get("/api/business-case")
    def business_case(
        cell: str = Query("0.5/2"),
        user: User = Depends(current_user),  # noqa: B008
    ) -> dict[str, Any]:
        d = wf().data
        st = d.table("cell_stress_results")
        st = st[st.cell == cell]
        ex = d.table("cell_excess_months")
        ex = ex[ex.cell == cell] if "cell" in ex else ex.iloc[0:0]
        return {
            "cell": cell,
            "verdicts": d.verdict(cell),
            "stress": _records(st.drop(columns=["cell"], errors="ignore")),
            "excess_months": _records(ex),
            "targets": d.config("acceptance_targets.yaml"),
            "battery": d.config("battery.yaml"),
            "capital": d.json("capital"),
            "sources": {
                k: d.manifest["tables"][k]
                for k in ("cell_verdicts", "cell_stress_results", "cell_excess_months")
            },
            "label": d.manifest["result_label"],
        }

    @app.get("/api/scenarios")
    def list_scenarios(user: User = Depends(current_user)) -> list[dict[str, Any]]:  # noqa: B008
        return [s.model_dump(mode="json") for s in wf().repo.list_scenarios()]

    @app.post("/api/scenarios")
    def create_scenario(
        body: ScenarioIn,
        user: User = Depends(require_operator),  # noqa: B008
    ) -> dict[str, Any]:
        allow = wf().allowlist["planning_agent"]["allowed_fields"]
        settings = body.model_dump(exclude={"name"})
        for k, v in settings.items():
            if v not in allow[k]:
                raise HTTPException(422, f"{k}={v} is not an allowed setting")
        return conflict(lambda: wf().create_scenario(body.name, settings, user.role)).model_dump(
            mode="json"
        )

    @app.get("/api/runs")
    def list_runs(user: User = Depends(current_user)) -> list[dict[str, Any]]:  # noqa: B008
        return [r.model_dump(mode="json") for r in wf().repo.list_runs()]

    @app.post("/api/runs")
    def start_run(body: RunIn, user: User = Depends(require_operator)) -> dict[str, Any]:  # noqa: B008
        run_id = conflict(lambda: wf().start(body.scenario_id, body.objective, body.concerns))
        return wf().detail(run_id)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, user: User = Depends(current_user)) -> dict[str, Any]:  # noqa: B008
        return conflict(lambda: wf().detail(run_id))

    @app.post("/api/runs/{run_id}/confirm")
    def confirm(
        run_id: str,
        body: ConfirmIn,
        user: User = Depends(require_operator),  # noqa: B008
    ) -> dict[str, Any]:
        conflict(lambda: wf().confirm(run_id, body.confirmed))
        return wf().detail(run_id)

    @app.post("/api/runs/{run_id}/decision")
    def decision(
        run_id: str,
        body: DecisionIn,
        user: User = Depends(require_operator),  # noqa: B008
    ) -> dict[str, Any]:
        conflict(lambda: wf().decide(run_id, body.decision, body.comment, user.identity_hash))
        return wf().detail(run_id)

    if STATIC.exists():
        app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            target = STATIC / path
            if path and target.is_file():
                return FileResponse(target)
            return FileResponse(STATIC / "index.html")

    return app


app = create_app()
