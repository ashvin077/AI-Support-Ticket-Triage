import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.agent.agent import agent
from src import config
from sqlalchemy import create_engine, text


URGENCIES = ["Critical", "High", "Medium", "Low"]
CATEGORIES = ["Billing", "Technical", "Account", "Feedback", "Other"]
SENTIMENTS = ["Angry", "Frustrated", "Neutral", "Happy"]
CANON = {v.lower(): v for v in URGENCIES + CATEGORIES + SENTIMENTS}
CANON["techical"] = "Technical"  # the prompt spells it this way

BASE = Path(__file__).parent


def run_agent() -> str:
    """Invoke the agent as in the original script (fresh thread per run)."""
    thread = {"configurable": {"thread_id": f"triage-{uuid.uuid4()}"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": ("Show the customer messages details to me")}]},
        thread,
    )
    return result["messages"][-1].content


def parse_table(md: str) -> list[dict]:
    """Turn the agent's pipe table into a list of ticket dicts."""
    rows = []
    for line in md.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or not cells[0].isdigit():
            continue  # header, separator or prose
        rows.append({
            "id": int(cells[0]),
            "message": " | ".join(cells[1:-4]),
            "urgency": CANON.get(cells[-4].lower(), cells[-4]),
            "category": CANON.get(cells[-3].lower(), cells[-3]),
            "sentiment": CANON.get(cells[-2].lower(), cells[-2]),
            "suggested_reply": cells[-1],
        })
    return rows


# Results live in Postgres, so they survive restarts and redeploys on any host.
# pool_pre_ping avoids errors from connections Neon closed while the database was idle.
store_engine = create_engine(config.NEON_DATABASE_URL, pool_pre_ping=True)


def init_store() -> None:
    with store_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS triage_results (
                id INTEGER PRIMARY KEY,
                message TEXT NOT NULL,
                urgency TEXT NOT NULL,
                category TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                suggested_reply TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )"""))


def load_store() -> dict:
    with store_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, message, urgency, category, sentiment, suggested_reply, updated_at "
            "FROM triage_results ORDER BY id")).mappings().all()
    tickets = [{k: v for k, v in r.items() if k != "updated_at"} for r in rows]
    updated = max((r["updated_at"] for r in rows), default=None)
    return {"tickets": tickets, "updated_at": updated.isoformat() if updated else None}


def save_store(tickets: list[dict]) -> None:
    """Replace the saved batch with a new one in a single transaction."""
    with store_engine.begin() as conn:
        conn.execute(text("DELETE FROM triage_results"))
        conn.execute(text(
            "INSERT INTO triage_results (id, message, urgency, category, sentiment, suggested_reply)"
            "VALUES (:id, :message, :urgency, :category, :sentiment, :suggested_reply)"), tickets)


def build_stats(tickets: list[dict]) -> dict:
    total = len(tickets)

    def counts(key, order):
        c = Counter(t[key] for t in tickets)
        labels = order + [k for k in c if k not in order]
        top = max(c.values(), default=1)
        return [{"label": k, "value": c.get(k, 0), "pct": round(100 * c.get(k, 0) / top)} for k in labels]

    pair = Counter((t["urgency"], t["category"]) for t in tickets)
    peak = max(pair.values(), default=1)
    heat = [{"label": u, "cells": [
        {"value": pair.get((u, c), 0), "alpha": round(0.15 + 0.85 * pair.get((u, c), 0) / peak, 2)}
        for c in CATEGORIES]} for u in URGENCIES]

    urgent = sum(t["urgency"] in ("Critical", "High") for t in tickets)
    upset = sum(t["sentiment"] in ("Angry", "Frustrated") for t in tickets)
    return {
        "total": total,
        "critical": sum(t["urgency"] == "Critical" for t in tickets),
        "urgent": urgent,
        "upset_pct": round(100 * upset / total) if total else 0,
        "urgency": counts("urgency", URGENCIES),
        "category": counts("category", CATEGORIES),
        "sentiment": counts("sentiment", SENTIMENTS),
        "heat": heat,
        "heat_cols": CATEGORIES,
    }


@asynccontextmanager
async def lifespan(_app):
    init_store()
    yield


app = FastAPI(title="Ticket Triage", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    data = load_store()
    rank = {u: i for i, u in enumerate(URGENCIES)}
    tickets = sorted(data["tickets"], key=lambda t: (rank.get(t["urgency"], 99), t["id"]))
    updated = None
    if data["updated_at"]:
        updated = datetime.fromisoformat(data["updated_at"]).astimezone(ZoneInfo("Asia/Kathmandu")).strftime("%d %b %Y, %H:%M")
    return templates.TemplateResponse(request, "index.html", {
        "tickets": tickets,
        "stats": build_stats(tickets),
        "updated": updated,
        "payload": {"tickets": tickets, "ranks": {"urgency": URGENCIES, "sentiment": SENTIMENTS}},
    })


@app.get("/api/tickets")
def get_tickets():
    return load_store()


@app.post("/api/triage")
def triage():
    try:
        raw = run_agent()
    except Exception as exc:
        raise HTTPException(502, f"The triage agent failed: {exc}")
    tickets = parse_table(raw)
    if not tickets:
        raise HTTPException(502, "The agent replied, but no ticket rows could be read. Run triage again.")
    tickets = list({t["id"]: t for t in tickets}.values())  # one row per ticket id
    try:
        save_store(tickets)
    except Exception as exc:
        raise HTTPException(500, f"Triage finished but the results could not be saved: {exc}")
    return load_store()
