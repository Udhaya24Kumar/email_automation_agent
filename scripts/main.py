import argparse
import hashlib
import json

from run_date import today_ist
from pathlib import Path

from gktoday_fetch import fetch_today_digest
from gktoday_quiz import fetch_today_quiz
from hindu_fetch import fetch_last_24h as fetch_hindu
from pib_fetch import fetch_today_releases as fetch_pib
from merge_sources import merge
from dedup import filter_new_items, save_seen
from gemini_filter import enrich_items, filter_low_relevance
from render_mail import build_html
from send_mail import send_email
from weekly_store import append_today as append_weekly_items

# scripts/main.py -> repo_root/data/seen_titles.json
SEEN_PATH = Path(__file__).resolve().parent.parent / "data" / "seen_titles.json"
# scripts/main.py -> repo_root/data/weekly_items.json
WEEKLY_PATH = Path(__file__).resolve().parent.parent / "data" / "weekly_items.json"


def _fetch_with_fallback(name, fn):
    try:
        items = fn()
    except Exception as exc:  # noqa: BLE001 - a broken source shouldn't kill the whole run
        print(f"{name} fetch failed ({exc}) — continuing with the other sources.")
        return []
    if not items:
        print(f"{name} returned no items this run.")
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path, help="Write HTML without sending or saving history")
    args = parser.parse_args()
    run_date = today_ist()
    today = run_date.strftime("%d %B %Y")

    # 1. Pull all three sources independently. Any one of them failing
    #    should degrade the digest, not kill the run.
    gktoday_items = _fetch_with_fallback("GKToday", fetch_today_digest)
    hindu_items = _fetch_with_fallback("The Hindu", fetch_hindu)
    pib_items = _fetch_with_fallback("PIB", fetch_pib)
    quiz = _fetch_with_fallback("GKToday quiz", fetch_today_quiz)

    quiz_id = hashlib.sha256(
        json.dumps(quiz, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    quiz_marker = f"Quiz delivery {quiz_id}"
    if quiz and not filter_new_items([{"title": quiz_marker}], SEEN_PATH, exact=True)[0]:
        quiz = []

    # 2. Merge + collapse cross-source duplicates (same story, different
    #    outlet) before we spend Gemini calls on it twice.
    merged = merge(gktoday_items, hindu_items, pib_items)

    # 3. Drop anything sent in the last N days (dedup.py), same as Phase 1.
    new_items, _ = filter_new_items(merged, SEEN_PATH)
    skipped = len(merged) - len(new_items)

    # 4. Gemini: SSC-relevance scoring, English summarisation and keywords
    #    (including translation of PIB Hindi releases). Hindi-only items are
    #    omitted if translation is unavailable.
    enriched = enrich_items(new_items)
    relevant_items = filter_low_relevance(enriched)
    filtered_low = len(enriched) - len(relevant_items)

    html = build_html(relevant_items, quiz, today)
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        args.preview.write_text(html, encoding="utf-8")
        print(f"Preview written to {args.preview}")
        return

    if not relevant_items and not quiz:
        print("Nothing new/relevant to send today. Skipping email.")
        return

    send_email(f"SSC Current Affairs — {today}", html)

    # Only mark items as seen once the email has actually gone out, so a
    # failed send doesn't silently swallow items on the next run.
    _, updated_seen = filter_new_items([
        {**item, "title": item.get("original_title") or item["title"]}
        for item in relevant_items
    ], SEEN_PATH)
    if quiz:
        updated_seen.append({
            "normalized": quiz_marker.lower(),
            "title": quiz_marker,
            "date_added": run_date.isoformat(),
        })
    save_seen(SEEN_PATH, updated_seen)

    # Feed today's sent items into the rolling 7-day store that
    # weekly_report.py reads from every Sunday. Same "only after a
    # successful send" rule as save_seen() above.
    append_weekly_items(WEEKLY_PATH, relevant_items, run_date.isoformat())

    print(
        f"Sent digest with {len(relevant_items)} news item(s) "
        f"[GKToday {len(gktoday_items)}, Hindu {len(hindu_items)}, PIB {len(pib_items)} raw; "
        f"{skipped} cross-source/historical duplicate(s), {filtered_low} low-relevance item(s) "
        f"dropped] and {len(quiz)} quiz question(s)."
    )


if __name__ == "__main__":
    main()
