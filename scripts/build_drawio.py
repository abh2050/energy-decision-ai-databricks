"""Build docs/architecture.drawio: EDIP production architecture diagrams (draw.io).

Pages: 1 platform architecture, 2 decision workflow, 3 agent guardrails, 4 data lineage,
5 CI/CD and environments, 6 security and governance. Icons are simplified vector
drawings in the style of the Databricks product family.

Usage: uv run python scripts/build_drawio.py
Render: drawio -x -f png -p N -o docs/diagrams/N.png docs/architecture.drawio  (N from 1)
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

OUT = Path("docs/architecture.drawio")
RED = "#FF3621"  # Databricks brand red-orange
NAVY = "#1B3139"

# Simplified SVG icons (64 x 64).
SVG = {
    "databricks": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<path d='M32 6 L58 20 L32 34 L6 20 Z' fill='{RED}'/>
<path d='M6 28 L32 42 L58 28 L58 34 L32 48 L6 34 Z' fill='{RED}'/>
<path d='M6 42 L32 56 L58 42 L58 48 L32 62 L6 48 Z' fill='{RED}'/></svg>""",
    "delta": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<path d='M32 6 L60 56 L4 56 Z' fill='#00ADD4'/><path d='M32 22 L48 50 L16 50 Z' fill='#fff'/>
<path d='M32 30 L42 47 L22 47 Z' fill='#003366'/></svg>""",
    "unity": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<path d='M32 4 L56 14 L56 34 C56 48 45 56 32 60 C19 56 8 48 8 34 L8 14 Z' fill='{NAVY}'/>
<rect x='20' y='20' width='10' height='10' fill='{RED}'/><rect x='34' y='20' width='10' height='10' fill='#fff'/>
<rect x='20' y='34' width='10' height='10' fill='#fff'/><rect x='34' y='34' width='10' height='10' fill='{RED}'/></svg>""",
    "mlflow": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='32' r='28' fill='#0194E2'/>
<path d='M14 42 L24 26 L32 36 L42 20 L50 30' stroke='#43C9ED' stroke-width='5' fill='none'/>
<path d='M14 46 L50 46' stroke='#fff' stroke-width='4'/></svg>""",
    "lakebase": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<ellipse cx='32' cy='14' rx='22' ry='8' fill='{RED}'/>
<path d='M10 14 L10 50 C10 55 20 58 32 58 C44 58 54 55 54 50 L54 14 C54 19 44 22 32 22 C20 22 10 19 10 14 Z' fill='{NAVY}'/>
<path d='M10 30 C10 35 20 38 32 38 C44 38 54 35 54 30' stroke='{RED}' stroke-width='3' fill='none'/></svg>""",
    "jobs": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<rect x='6' y='10' width='52' height='44' rx='6' fill='{NAVY}'/>
<path d='M16 22 L28 32 L16 42' stroke='{RED}' stroke-width='5' fill='none'/>
<rect x='32' y='38' width='18' height='5' fill='#fff'/></svg>""",
    "apps": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<rect x='4' y='8' width='56' height='48' rx='6' fill='{NAVY}'/><rect x='4' y='8' width='56' height='10' rx='4' fill='{RED}'/>
<rect x='12' y='26' width='18' height='22' fill='#fff'/><rect x='34' y='26' width='18' height='10' fill='#fff'/>
<rect x='34' y='40' width='18' height='8' fill='#fff'/></svg>""",
    "model": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='32' r='28' fill='{NAVY}'/>
<path d='M32 12 L36 28 L52 32 L36 36 L32 52 L28 36 L12 32 L28 28 Z' fill='{RED}'/></svg>""",
    "volume": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<path d='M6 16 L26 16 L30 22 L58 22 L58 54 L6 54 Z' fill='{NAVY}'/>
<rect x='12' y='30' width='40' height='4' fill='{RED}'/><rect x='12' y='40' width='28' height='4' fill='#fff'/></svg>""",
    "user": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='20' r='12' fill='#475569'/><path d='M8 58 C8 40 20 36 32 36 C44 36 56 40 56 58 Z' fill='#475569'/></svg>""",
    "github": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='32' r='28' fill='#24292F'/>
<path d='M20 44 C20 34 24 30 32 30 C40 30 44 34 44 44 Z M22 22 L26 30 M42 22 L38 30' stroke='#fff' stroke-width='4' fill='#fff'/></svg>""",
    "browser": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<rect x='4' y='8' width='56' height='48' rx='6' fill='#0369A1'/><rect x='4' y='8' width='56' height='10' rx='4' fill='#7DD3FC'/>
<circle cx='12' cy='13' r='2' fill='#0369A1'/><path d='M14 44 L24 32 L32 40 L44 26 L52 34' stroke='#fff' stroke-width='4' fill='none'/></svg>""",
    "data": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<path d='M14 4 L42 4 L54 16 L54 60 L14 60 Z' fill='#64748B'/><path d='M42 4 L42 16 L54 16 Z' fill='#CBD5E1'/>
<rect x='22' y='28' width='24' height='4' fill='#fff'/><rect x='22' y='38' width='24' height='4' fill='#fff'/></svg>""",
    "check": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='32' cy='32' r='28' fill='#16A34A'/><path d='M18 33 L28 43 L47 22' stroke='#fff' stroke-width='6' fill='none'/></svg>""",
    "shield": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<path d='M32 4 L56 14 L56 32 C56 46 45 56 32 60 C19 56 8 46 8 32 L8 14 Z' fill='#B45309'/>
<path d='M22 32 L30 40 L44 24' stroke='#fff' stroke-width='5' fill='none'/></svg>""",
    "key": f"""<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<circle cx='22' cy='32' r='14' fill='{NAVY}'/><circle cx='22' cy='32' r='5' fill='#fff'/>
<rect x='34' y='28' width='26' height='8' fill='{NAVY}'/><rect x='50' y='36' width='6' height='10' fill='{RED}'/></svg>""",
    "actions": """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>
<rect x='4' y='4' width='56' height='56' rx='12' fill='#2088FF'/>
<circle cx='20' cy='22' r='6' fill='#fff'/><circle cx='44' cy='42' r='6' fill='#fff'/>
<path d='M20 28 L20 42 L38 42' stroke='#fff' stroke-width='4' fill='none'/></svg>""",
}


def _text(label: str) -> str:
    """Attribute-safe HTML label; newlines become line breaks."""
    return html.escape(label).replace("\n", "&lt;br&gt;")


def img(name: str) -> str:
    b64 = base64.b64encode(SVG[name].encode()).decode()
    return f"data:image/svg+xml,{b64}"


class Page:
    def __init__(self, name: str) -> None:
        self.name = name
        self.cells: list[str] = []
        self.n = 2

    def _id(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def box(self, label: str, x: int, y: int, w: int, h: int, style: str, parent: str = "1") -> str:
        i = self._id()
        self.cells.append(
            f'<mxCell id="{i}" value="{_text(label)}" style="{style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
        )
        return i

    def zone(
        self,
        label: str,
        x: int,
        y: int,
        w: int,
        h: int,
        color: str = "#F8FAFC",
        stroke: str = "#94A3B8",
    ) -> str:
        return self.box(
            label,
            x,
            y,
            w,
            h,
            f"rounded=1;arcSize=3;whiteSpace=wrap;html=1;fillColor={color};strokeColor={stroke};"
            "verticalAlign=top;align=left;spacingLeft=10;spacingTop=6;fontStyle=1;fontSize=14;"
            "dashed=1;container=0;zone=1;",
        )

    def icon(self, name: str, label: str, x: int, y: int, size: int = 48, width: int = 150) -> str:
        """Icon centred in a column of `width`, with its label as a separate text cell
        below (so the label is not squeezed into the icon's width)."""
        style = f"shape=image;html=1;imageAspect=0;aspect=fixed;image={img(name)};"
        i = self._id()
        self.cells.append(
            f'<mxCell id="{i}" value="" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x + (width - size) // 2}" y="{y}" width="{size}" height="{size}" as="geometry"/></mxCell>'
        )
        self.box(
            label,
            x,
            y + size + 4,
            width,
            44,
            "text;html=1;whiteSpace=wrap;align=center;verticalAlign=top;fontSize=11;"
            "labelBackgroundColor=#FFFFFF;",
        )
        return i

    def card(
        self,
        label: str,
        x: int,
        y: int,
        w: int = 180,
        h: int = 60,
        fill: str = "#FFFFFF",
        stroke: str = "#334155",
        bold: bool = False,
    ) -> str:
        return self.box(
            label,
            x,
            y,
            w,
            h,
            f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontSize=11;"
            + ("fontStyle=1;" if bold else ""),
        )

    def diamond(self, label: str, x: int, y: int, w: int = 150, h: int = 80) -> str:
        return self.box(
            label,
            x,
            y,
            w,
            h,
            "rhombus;whiteSpace=wrap;html=1;fillColor=#FEF3C7;strokeColor=#B45309;fontSize=11;",
        )

    def note(self, label: str, x: int, y: int, w: int, h: int) -> str:
        return self.box(
            label,
            x,
            y,
            w,
            h,
            "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=11;fontColor=#475569;",
        )

    def arrow(
        self,
        a: str,
        b: str,
        label: str = "",
        dashed: bool = False,
        color: str = "#334155",
        extra: str = "",
        points: list[tuple[int, int]] | None = None,
    ) -> str:
        i = self._id()
        style = (
            f"edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;strokeColor={color};"
            f"fontSize=10;labelBackgroundColor=#FFFFFF;" + ("dashed=1;" if dashed else "") + extra
        )
        self.cells.append(
            f'<mxCell id="{i}" value="{html.escape(label)}" style="{style}" edge="1" parent="1" source="{a}" target="{b}">'
            '<mxGeometry relative="1" as="geometry">'
            + (
                '<Array as="points">'
                + "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points)
                + "</Array>"
                if points
                else ""
            )
            + "</mxGeometry></mxCell>"
        )
        return i

    def xml(self, idx: int) -> str:
        # Edges first, so shapes and labels are drawn on top of the arrows.
        zones = [c for c in self.cells if "zone=1;" in c]
        edges = [c for c in self.cells if ' edge="1"' in c]
        rest = [c for c in self.cells if c not in zones and c not in edges]
        body = "".join(zones + edges + rest)
        return (
            f'<diagram id="p{idx}" name="{html.escape(self.name)}"><mxGraphModel dx="1600" dy="1000" grid="1" '
            'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            'pageWidth="1920" pageHeight="1180" math="0" shadow="0"><root><mxCell id="0"/>'
            f'<mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram>'
        )


def title(p: Page, text: str, sub: str) -> None:
    p.box(text, 20, 10, 1600, 30, "text;html=1;fontSize=20;fontStyle=1;align=left;")
    p.note(sub, 20, 40, 1700, 30)


def legend(p: Page, y: int) -> None:
    p.note(
        "Solid arrows: run-time data flow or calls. Dashed arrows: governance, deployment, or control.",
        20,
        y,
        1400,
        24,
    )


TOP = "exitX=0.5;exitY=0;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
RIGHT = "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;"


def architecture() -> Page:
    p = Page("1 Platform architecture")
    title(
        p,
        "Energy Decision Intelligence Platform: platform architecture",
        "Serverless Databricks lakehouse on AWS (us-east-1). Unity Catalog governs all data and models; operational state in Lakebase; agents on the Foundation Model API.",
    )
    p.zone("Sources and users", 20, 80, 200, 780)
    meter = p.icon("data", "Metered facility load (15 minute interval data)", 30, 120, width=180)
    tar = p.icon(
        "data", "Utility tariff schedules (PG&E B-19, PGE Schedule 85)", 30, 290, width=180
    )
    users = p.icon("user", "Energy operators (approve) and viewers (read only)", 30, 680, width=180)

    p.zone("Databricks Data Intelligence Platform (serverless)", 240, 80, 1420, 780, "#FFF7F5", RED)
    p.icon("databricks", "Databricks", 1540, 95, 36, 110)
    # Row 1: ingestion and ML.
    raw = p.icon(
        "volume", "Unity Catalog volume: raw snapshots (versioned, SHA256)", 260, 130, width=180
    )
    cur = p.icon(
        "delta", "Delta (curated): hourly and 15 min load, features, forecasts", 470, 130, width=190
    )
    train = p.icon("jobs", "Lakeflow Jobs: ingest, train, calibrate", 690, 130, width=170)
    mlf = p.icon("mlflow", "MLflow: experiments, Unity Catalog model registry", 890, 130, width=180)
    model = p.icon(
        "model", "Load forecaster (LightGBM point + P10/P50/P90, conformal)", 1100, 130, width=200
    )
    # Row 2: optimization.
    replay = p.icon(
        "jobs", "Lakeflow Jobs: dispatch replay, stress tests, sensitivity", 470, 310, width=190
    )
    opt = p.card(
        "Optimization and settlement engine\ndaily MILP (HiGHS), 15 min billing demand,\ncharge guard, tariff calendars",
        700,
        300,
        300,
        70,
    )
    # Row 3: decision marts and publishing.
    snap = p.icon(
        "volume", "Serving snapshot volume (Delta versions, manifest)", 260, 480, width=180
    )
    pub = p.icon("jobs", "Lakeflow Job: publish serving snapshot", 470, 480, width=190)
    ev = p.icon(
        "delta",
        "Delta (eval): strategy results, sensitivity grid, stress results, decision verdicts, agent evaluations",
        710,
        480,
        width=230,
    )
    uc = p.icon(
        "unity",
        "Unity Catalog: catalog edip (raw, curated, ml, eval), grants, lineage",
        1000,
        480,
        width=220,
    )
    # Row 4: decision service.
    app = p.icon(
        "apps", "Databricks App: decision workspace (FastAPI + React)", 260, 680, width=190
    )
    lb = p.icon(
        "lakebase",
        "Lakebase (PostgreSQL): scenarios, runs, checkpoints, approvals, agent calls",
        500,
        680,
        width=210,
    )
    sec = p.icon("key", "Secret scope: role configuration", 760, 680, width=170)
    fm = p.icon(
        "model",
        "Foundation Model API: Llama 3.3 70B (planning, risk, business agents)",
        980,
        680,
        width=210,
    )
    tr = p.icon("mlflow", "MLflow Tracing: agent spans", 1240, 680, width=170)
    p.card(
        "Agent guardrails in code: allowlisted changes, evidence-validated claims and comparisons, deterministic verdicts, one call per agent, deterministic fallback",
        1440,
        660,
        205,
        120,
        "#FEF3C7",
        "#B45309",
    )

    p.arrow(meter, raw, "ingest")
    p.arrow(tar, raw, "load", extra="entryX=0;entryY=0.8;entryDx=0;entryDy=0;")
    p.arrow(raw, cur, "parse, validate")
    p.arrow(cur, train, "features")
    p.arrow(train, mlf, "log, register")
    p.arrow(mlf, model, "serve version")
    p.arrow(cur, replay, "load, forecasts")
    p.arrow(replay, opt, "solve, settle")
    p.arrow(replay, ev, "persist")
    p.arrow(uc, ev, "governs", dashed=True)
    p.arrow(ev, pub, "read")
    p.arrow(pub, snap, "write")
    p.arrow(snap, app, "evidence")
    p.arrow(users, app, "SSO (OAuth)")
    p.arrow(app, lb, "state")
    p.arrow(app, fm, "agent calls", extra=TOP)
    p.arrow(app, sec, "roles", extra=TOP)
    p.arrow(fm, tr, "traces", dashed=True)
    legend(p, 880)
    return p


def workflow() -> Page:
    p = Page("2 Decision workflow")
    title(
        p,
        "Decision workflow: operator request to operator decision",
        "Every step is checkpointed in Lakebase. Each agent makes at most one model call per run. Only the operator approves.",
    )
    xs = [20, 280, 540, 800, 1060, 1320, 1580]
    op = p.icon("user", "Operator", xs[0] + 20, 90)
    s1 = p.card("1. Operator request\nobjective and concerns", xs[0], 190, 200, 60, bold=True)
    s2 = p.card(
        "2. Planning agent\ntyped scenario change,\nquoting the request",
        xs[1],
        185,
        200,
        70,
        "#FEF3C7",
        "#B45309",
    )
    s3 = p.diamond("3. Operator\nconfirms change?", xs[2] + 20, 180, 160, 80)
    s4 = p.card("4. Forecast\nP10 / P50 / P90 load", xs[3], 190, 200, 60)
    s5 = p.card("5. Optimization\ndaily MILP per strategy", xs[4], 190, 200, 60)
    s6 = p.card(
        "6. Settlement and validation\n15 min billing, constraint checks", xs[5], 190, 200, 60
    )
    s7 = p.card("7. Risk agent\nselects stress tests", xs[5], 340, 200, 60, "#FEF3C7", "#B45309")
    st = p.card("Stress tests\nforecast error, heat week,\nreserve floor", xs[4], 335, 200, 70)
    vd = p.card(
        "Deterministic verdicts\nfrozen rule + amendment A1",
        xs[3],
        340,
        200,
        60,
        "#DCFCE7",
        "#16A34A",
        True,
    )
    s8 = p.card(
        "8. Business agent\nexplains the verdict,\nscope, evidence",
        xs[2],
        335,
        200,
        70,
        "#FEF3C7",
        "#B45309",
    )
    s9 = p.diamond("9. Operator decision\napprove / revise / reject", xs[1] + 10, 325, 180, 90)
    lb = p.icon(
        "lakebase", "Lakebase: checkpoints, agent calls, approvals", xs[0] + 10, 340, width=180
    )
    fb = p.card("Deterministic fallback summary", xs[2], 500, 200, 50, "#F1F5F9", "#64748B")
    p.arrow(op, s1)
    p.arrow(s1, s2)
    p.arrow(s2, s3)
    p.arrow(s3, s4, "yes")
    p.arrow(s4, s5)
    p.arrow(s5, s6)
    p.arrow(s6, s7)
    p.arrow(s7, st)
    p.arrow(st, vd)
    p.arrow(vd, s8)
    p.arrow(s8, s9)
    p.arrow(s9, lb, "persist")
    p.arrow(
        s2,
        fb,
        "rejected",
        dashed=True,
        color="#64748B",
        extra="exitX=1;exitY=0.8;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;",
    )
    p.arrow(s8, fb, "rejected", dashed=True, color="#64748B")
    p.note(
        "Hard constraints are not on the planning allowlist. Agents never approve, operate equipment, export power, or trade.",
        20,
        590,
        1300,
        24,
    )
    legend(p, 620)
    return p


def guardrails() -> Page:
    p = Page("3 Agent guardrails")
    title(
        p,
        "Agent guardrails: every response is validated against evidence in code",
        "Order of checks for one agent call. Any rejection, timeout, or error returns the deterministic summary; calls are never retried.",
    )
    ev = p.icon(
        "delta", "Evidence packet: governed Delta rows + acceptance targets", 20, 100, width=200
    )
    budget = p.card("Call budget\none call per agent per run", 250, 110, 180, 50)
    call = p.icon(
        "model", "Foundation Model API (JSON schema, deadline, no retry)", 460, 100, width=200
    )
    c1 = p.diamond("Schema\nvalid?", 720, 95, 140, 80)
    c2 = p.diamond("Citations exist?\nnumbers match?", 900, 95, 170, 80)
    c3 = p.diamond("Comparisons typed\nand true?", 1110, 95, 170, 80)
    c4 = p.diamond("Planning: allowlisted\nfield, quoted request", 1110, 250, 190, 90)
    c5 = p.diamond("Business: matches\nA1 verdict?", 1370, 255, 170, 80)
    ok = p.icon("check", "Validated response shown with evidence links", 1580, 265, width=170)
    fx, fw = 720, 880
    fb = p.card(
        "Deterministic summary (rule-based), shown in place of the rejected response",
        fx,
        440,
        fw,
        50,
        "#F1F5F9",
        "#64748B",
        True,
    )
    tr = p.icon(
        "mlflow",
        "MLflow Tracing: prompt version, status, latency, tokens, reasons",
        900,
        560,
        width=220,
    )
    lbc = p.icon(
        "lakebase", "Lakebase agent_calls (one row per agent per run)", 1220, 560, width=210
    )
    p.arrow(ev, budget)
    p.arrow(budget, call)
    p.arrow(call, c1)
    p.arrow(c1, c2, "yes")
    p.arrow(c2, c3, "yes")
    p.arrow(c3, c4, "yes")
    p.arrow(c4, c5, "yes")
    p.arrow(c5, ok, "yes")

    def down(c: str, cx: int, label: str = "no") -> None:
        ex = (cx - fx) / fw
        p.arrow(
            c,
            fb,
            label,
            dashed=True,
            color="#B91C1C",
            extra=f"exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX={ex:.3f};entryY=0;entryDx=0;entryDy=0;",
        )

    down(c1, 790)
    down(c2, 985)
    down(c4, 1205)
    down(c5, 1455)
    p.arrow(
        c3,
        fb,
        "no",
        dashed=True,
        color="#B91C1C",
        extra=f"exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX={(1320 - fx) / fw:.3f};entryY=0;entryDx=0;entryDy=0;",
        points=[(1320, 135)],
    )
    p.arrow(fb, tr, "record", extra="exitX=0.25;exitY=1;exitDx=0;exitDy=0;")
    p.arrow(tr, lbc)
    legend(p, 680)
    return p


def lineage() -> Page:
    p = Page("4 Data lineage")
    title(
        p,
        "Data lineage: governed medallion layers from metered load to decisions",
        "All tables live in Unity Catalog catalog edip. Every value shown to an operator carries its source table and Delta version.",
    )
    p.zone("Raw", 20, 80, 260, 600, "#F8FAFC")
    p.zone("Curated", 300, 80, 540, 600, "#F0F9FF", "#0369A1")
    p.zone("Decision marts (eval)", 860, 80, 580, 600, "#F0FDF4", "#16A34A")
    p.zone("Serving", 1460, 80, 280, 600, "#FFF7F5", RED)
    raw = p.icon(
        "volume",
        "raw.snapshots: load files, tariff schedules (versioned, hashed)",
        40,
        140,
        width=220,
    )
    lo = p.icon("delta", "load_observations (hourly) + load_intervals_15min", 320, 140, width=230)
    fp = p.icon("delta", "forecast_predictions (pinned model version)", 590, 140, width=230)
    rep = p.icon(
        "delta", "dispatch_schedules, settlement_outcomes, replay_outcomes", 590, 330, width=230
    )
    grid = p.icon("delta", "sensitivity_grid", 880, 140, width=240)
    stress = p.icon(
        "delta", "stress_results, stress_excess_months, stress_peak_moments", 880, 330, width=240
    )
    cells = p.icon(
        "delta", "cell_* (annual, stress, verdicts, evidence, schedules)", 880, 520, width=240
    )
    verd = p.icon("delta", "decision_verdicts, agent_evaluations", 1180, 520, width=240)
    snap = p.icon("volume", "Serving snapshot + manifest", 1490, 330, width=220)
    app = p.icon("apps", "Decision workspace (Databricks App)", 1490, 520, width=220)
    p.arrow(raw, lo, "ingest job")
    p.arrow(lo, fp, "forecast job")
    p.arrow(fp, rep, "replay job")
    p.arrow(fp, grid, "sensitivity job")
    p.arrow(rep, stress, "stress job")
    p.arrow(
        rep,
        cells,
        "evidence job",
        extra="exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;",
        points=[(705, 544)],
    )
    p.arrow(cells, verd, "verdicts")
    p.arrow(stress, snap, "publish job")
    p.arrow(
        verd,
        snap,
        "",
        extra="exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.75;entryDx=0;entryDy=0;",
    )
    p.arrow(snap, app, "read-only")
    legend(p, 700)
    return p


def cicd() -> Page:
    p = Page("5 CI/CD and environments")
    title(
        p,
        "CI/CD and environments: GitHub Actions with Databricks Asset Bundles",
        "Every workspace resource is declared in the bundle and deployed per target; nothing is created by hand.",
    )
    repo = p.icon("github", "GitHub repository (main, pull requests)", 20, 130, width=180)
    ci = p.icon("actions", "GitHub Actions", 230, 130, width=150)
    checks = p.card(
        "Quality gates\nRuff lint and format, pytest,\nPlaywright end-to-end,\nsecret scan, bundle validate",
        410,
        115,
        240,
        90,
    )
    bundle = p.icon(
        "databricks", "Databricks Asset Bundle (databricks.yml, resources)", 690, 130, width=200
    )
    dev = p.zone("dev target", 960, 80, 320, 260, "#F8FAFC")
    prod = p.zone("prod target", 1400, 80, 320, 260, "#FFF7F5", RED)
    for x, name in ((980, "dev"), (1420, "prod")):
        p.card(f"Lakeflow Jobs ({name})", x, 120, 135, 40)
        p.card("Databricks App", x + 145, 120, 135, 40)
        p.card("Lakebase project", x, 180, 135, 40)
        p.card("UC schemas + volumes", x + 145, 180, 135, 40)
        p.card("Foundation Model API access", x, 240, 280, 40)
    mon = p.icon(
        "mlflow",
        "Monitoring: MLflow runs and traces, job runs, budget alerts",
        1360,
        420,
        width=200,
    )
    lb = p.icon(
        "lakebase", "Lakebase audit trail: runs, approvals, agent calls", 1570, 420, width=200
    )
    p.arrow(repo, ci, "push / PR")
    p.arrow(ci, checks, "run")
    p.arrow(checks, bundle, "pass")
    p.arrow(bundle, dev, "deploy", extra="entryX=0;entryY=0.285;entryDx=0;entryDy=0;")
    p.arrow(dev, prod, "promote")
    p.arrow(prod, mon, "", dashed=True, extra="exitX=0.3;exitY=1;exitDx=0;exitDy=0;")
    p.arrow(prod, lb, "", dashed=True, extra="exitX=0.7;exitY=1;exitDx=0;exitDy=0;")
    legend(p, 540)
    return p


def security() -> Page:
    p = Page("6 Security and governance")
    title(
        p,
        "Security and governance",
        "Least privilege for every principal; identities never stored in clear text; hard constraints enforced in code.",
    )
    users = p.icon("user", "Operators and viewers", 20, 120, width=170)
    sso = p.icon("key", "Workspace SSO (OAuth) at the Databricks Apps proxy", 220, 120, width=200)
    app = p.icon(
        "apps", "Decision workspace: server-side roles (operator, viewer)", 450, 120, width=210
    )
    sp = p.icon("shield", "App service principal (least privilege)", 700, 120, width=190)
    uc = p.icon(
        "unity",
        "Unity Catalog: USE CATALOG, USE SCHEMA, READ VOLUME (serving snapshot only)",
        1100,
        90,
        width=330,
    )
    lb = p.icon(
        "lakebase",
        "Lakebase role: SELECT, INSERT, UPDATE on five tables (no DELETE, no DDL)",
        1100,
        220,
        width=330,
    )
    fm = p.icon("model", "Serving endpoint: CAN_QUERY only", 1100, 350, width=330)
    sec = p.icon(
        "key", "Secret scope: salted hashes of operator identities (READ)", 1100, 480, width=330
    )
    p.card(
        "Approvals store a salted identity hash, never an email.\nAgents cannot change hard constraints, approve,\noperate equipment, export power, or trade.",
        450,
        330,
        400,
        80,
        "#FEF3C7",
        "#B45309",
    )
    p.card(
        "CI blocks credentials, workspace URLs, tokens,\nand emails from the repository (secret scan).",
        20,
        330,
        380,
        60,
        "#F1F5F9",
        "#64748B",
    )
    p.arrow(users, sso, "sign in")
    p.arrow(sso, app, "identity headers")
    p.arrow(app, sp, "acts as")
    for target, y in ((uc, 114), (lb, 244), (fm, 374), (sec, 504)):
        p.arrow(
            sp,
            target,
            "",
            extra="exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;",
            points=[(980, 144), (980, y)],
        )
    legend(p, 600)
    return p


def main() -> int:
    pages = [architecture(), workflow(), guardrails(), lineage(), cicd(), security()]
    xml = (
        '<mxfile host="edip-build" agent="scripts/build_drawio.py" version="24.0.0">'
        + "".join(pg.xml(i + 1) for i, pg in enumerate(pages))
        + "</mxfile>\n"
    )
    OUT.write_text(xml)
    print(f"{OUT}: {len(pages)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
