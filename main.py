import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json

from src.agent.agent import agent

URGENCIES = ["Critical", "High", "Medium", "Low"]
CATEGORIES = ["Billing", "Technical", "Account", "Feedback", "Other"]
SENTIMENTS = ["Angry", "Frustrated", "Neutral", "Happy"]
CANON = {v.lower(): v for v in URGENCIES + CATEGORIES + SENTIMENTS}
CANON["techical"] = "Technical"  # the prompt spells it this way

BASE = Path(__file__).parent
STORE = BASE / "triage_results.json"


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


def load_store() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text(encoding="utf-8"))
    return {"tickets": [], "updated_at": None}


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


app = FastAPI(title="Ticket Triage")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    data = load_store()
    rank = {u: i for i, u in enumerate(URGENCIES)}
    tickets = sorted(data["tickets"], key=lambda t: (rank.get(t["urgency"], 99), t["id"]))
    updated = None
    if data["updated_at"]:
        updated = datetime.fromisoformat(data["updated_at"]).astimezone().strftime("%d %b %Y, %H:%M")
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
    data = {"tickets": tickets, "updated_at": datetime.now(timezone.utc).isoformat()}
    STORE.write_text(json.dumps(data), encoding="utf-8")
    return data
