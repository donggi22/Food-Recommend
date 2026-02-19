"""Logging: input context summary + output to file."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.models import Context, ReasonResponse

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def log_reason_call(context: Context, top_k: list[int], response: ReasonResponse, case_id: Optional[str] = None) -> None:
    """Append one log line (context summary + output) to logs/reason_calls.jsonl."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    context_summary = {
        "meal_slot": context.meal_slot,
        "hunger_level": context.hunger_level,
        "mood": context.mood,
        "company": context.company,
        "effort_level": context.effort_level,
        "budget_range": context.budget_range,
    }
    if context.weather:
        context_summary["weather"] = {
            "condition": context.weather.condition,
            "temp_c": context.weather.temp_c,
        }
    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "case_id": case_id,
        "context_summary": context_summary,
        "top_k": top_k,
        "output": {
            "selected_menu_id": response.selected_menu_id,
            "reason_one_liner": response.reason_one_liner,
            "reason_tags": response.reason_tags,
        },
    }
    path = LOG_DIR / "reason_calls.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
