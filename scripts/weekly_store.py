"""
Rolling 7-day store of everything actually emailed in the daily digest,
used to build the Sunday weekly PDF report.

Kept deliberately separate from dedup.py's seen_titles.json: that file only
tracks normalized titles for duplicate-detection and is pruned on a
different (5-day) retention window. This file keeps the fields the weekly
report needs (title, summary, category, source, url, importance) and is
pruned to a 7-day window, so it never grows unbounded even if the weekly
report workflow is ever disabled.

main.py calls append_today() once per successful run, right after the
digest email sends. weekly_report.py calls load_week() to read it back.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

RETENTION_DAYS = 7

# Only the fields the weekly report actually renders are kept — no need to
# duplicate the full enriched item (keywords, relevance, also_reported_by).
WEEKLY_FIELDS = ("title", "summary", "category", "source", "url", "importance")


def _prune(entries: list[dict]) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    kept = []
    for entry in entries:
        try:
            added = datetime.fromisoformat(entry["date_added"])
        except (KeyError, ValueError):
            continue
        if added >= cutoff:
            kept.append(entry)
    return kept


def load_week(path: Path) -> list[dict]:
    """Return the last RETENTION_DAYS days of stored items, oldest first."""
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    entries = _prune(data.get("items", []))
    entries.sort(key=lambda e: e.get("date_added", ""))
    return entries


def append_today(path: Path, items: list[dict], today_iso: str) -> None:
    """Append today's sent items to the rolling weekly store.

    `items` should be the same relevant/enriched items that went out in
    today's digest email. Only called after a successful send, mirroring
    dedup.py's save_seen() — a failed send shouldn't add anything here
    either.
    """
    existing = _prune(_load_raw(path))

    for item in items:
        entry = {field: item.get(field, "") for field in WEEKLY_FIELDS}
        entry["date_added"] = today_iso
        existing.append(entry)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"items": existing}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_raw(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("items", [])
