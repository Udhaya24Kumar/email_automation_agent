"""
Lightweight duplicate detection using a JSON file committed back to the repo.

GitHub Actions runners are wiped after every run, so "have I already sent
this" needs to live somewhere persistent. A small JSON file in the repo,
updated and committed at the end of each run, is the simplest option that
doesn't need an external database at this scale (one write per day).
"""
import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

RETENTION_DAYS = 5
SIMILARITY_THRESHOLD = 0.82


def normalize(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def load_seen(path):
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        # File exists but is empty (e.g. created by `touch` before its
        # first real write) — treat the same as "no history yet".
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"Warning: {path} contains invalid JSON — treating as empty.")
        return []

    return data.get("items", [])

def save_seen(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"items": entries},
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )



def _prune(entries: list[dict]) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    kept = []
    for e in entries:
        try:
            added = datetime.fromisoformat(e["date_added"])
        except (KeyError, ValueError):
            continue
        if added >= cutoff:
            kept.append(e)
    return kept


def _is_duplicate(norm_title: str, seen: list[dict]) -> bool:
    for e in seen:
        if SequenceMatcher(None, norm_title, e["normalized"]).ratio() >= SIMILARITY_THRESHOLD:
            return True
    return False


def filter_new_items(items: list[dict], seen_path: Path) -> tuple[list[dict], list[dict]]:
    """Return (new_items, updated_seen_entries).

    Only call save_seen() with the updated entries AFTER the email has sent
    successfully — otherwise a failed send would still mark items as seen
    and you'd silently lose them.
    """
    seen = _prune(load_seen(seen_path))
    new_items = []
    today = datetime.now().date().isoformat()
    for item in items:
        norm = normalize(item["title"])
        if _is_duplicate(norm, seen):
            continue
        new_items.append(item)
        seen.append({"normalized": norm, "title": item["title"], "date_added": today})
    return new_items, seen
