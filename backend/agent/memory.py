"""Workflow memory — the agent remembers walkthroughs it has already planned.

Parsing a document costs a Claude call and a few seconds. Once a workflow has
been planned successfully, we persist it so the next demo of the same product
starts instantly. Storage is a single JSON file: no database, no migrations,
and the whole thing is diffable in a PR.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from . import config
from .models import StepPlan

log = logging.getLogger(__name__)


def _load_raw() -> dict[str, Any]:
    if not config.WORKFLOWS_PATH.exists():
        return {"workflows": {}}
    try:
        return json.loads(config.WORKFLOWS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Workflow memory unreadable (%s) — starting fresh", exc)
        return {"workflows": {}}


def _write_raw(data: dict[str, Any]) -> None:
    config.WORKFLOWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.WORKFLOWS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def list_workflows() -> list[dict[str, Any]]:
    """Summarise everything the agent has learned, newest first."""
    entries = [
        {
            "name": name,
            "summary": entry.get("plan", {}).get("summary", ""),
            "steps": len(entry.get("plan", {}).get("steps", [])),
            "runs": entry.get("runs", 0),
            "last_run": entry.get("last_run"),
        }
        for name, entry in _load_raw().get("workflows", {}).items()
    ]
    return sorted(entries, key=lambda e: e.get("last_run") or "", reverse=True)


def recall(name: str) -> StepPlan | None:
    """Return a previously learned plan, or None if this is a first encounter."""
    entry = _load_raw().get("workflows", {}).get(name)
    if not entry:
        return None
    try:
        plan = StepPlan.model_validate(entry["plan"])
    except Exception as exc:  # stored schema predates a model change
        log.warning("Stored workflow %r no longer validates (%s)", name, exc)
        return None
    log.info("Recalled workflow %r from memory (%d steps)", name, len(plan.steps))
    return plan


def remember(plan: StepPlan) -> None:
    """Persist a plan under its workflow name and bump the run counter."""
    data = _load_raw()
    workflows = data.setdefault("workflows", {})
    entry = workflows.get(plan.workflow_name, {"runs": 0})
    entry["plan"] = plan.model_dump(mode="json")
    entry["runs"] = entry.get("runs", 0) + 1
    entry["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    workflows[plan.workflow_name] = entry
    _write_raw(data)
    log.info("Remembered workflow %r (run #%d)", plan.workflow_name, entry["runs"])


def forget(name: str) -> bool:
    """Drop a workflow so the next run re-plans it from the document."""
    data = _load_raw()
    if name in data.get("workflows", {}):
        del data["workflows"][name]
        _write_raw(data)
        return True
    return False
