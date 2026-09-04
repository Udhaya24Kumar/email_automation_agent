"""
Fetch the last 24 hours of headlines from The Hindu's public RSS feeds.

The Hindu runs a standard per-section RSS feed (title/link/description/
pubDate). We pull a handful of section feeds that map cleanly onto our 9 SSC
buckets and keep only items published in the last 24 hours, since (unlike
GKToday) these feeds aren't already curated down to "today's current
affairs" — they're the raw section firehose.

This is our second raw source (Phase 2): keyword-based categorisation
(FEED_SECTIONS below already gives us the category for free, since each
feed *is* a section), used mainly to catch stories GKToday's editors didn't
pick up, and to cross-verify what GKToday reported.
"""

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

# (feed URL, our category bucket) — one feed per SSC section we can map
# cleanly. The Hindu doesn't have dedicated "Awards", "Reports & Indexes" or
# "Important Days" feeds, so those buckets are filled mostly by GKToday;
# any Hindu item whose title matches AWARD_KEYWORDS below gets bumped into
# "awards" regardless of which feed it came from.
FEED_SECTIONS = [
    ("https://www.thehindu.com/news/national/feeder/default.rss", "national"),
    ("https://www.thehindu.com/news/international/feeder/default.rss", "international"),
    ("https://www.thehindu.com/business/Economy/feeder/default.rss", "economy"),
    ("https://www.thehindu.com/sci-tech/science/feeder/default.rss", "science"),
    ("https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss", "environment"),
    ("https://www.thehindu.com/sport/feeder/default.rss", "sports"),
]

LOOKBACK_HOURS = 24

AWARD_KEYWORDS = re.compile(
    r"\b(award|honour|honor|appointed|appoint(s|ed)?|felicitat|laureate|prize)\b",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SSC-CA-Digest/0.2; personal study tool)"
}


def _parse_pubdate(entry) -> datetime | None:
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _clean_excerpt(summary: str) -> str:
    # feedparser leaves HTML in the summary sometimes; strip tags crudely.
    text = re.sub(r"<[^>]+>", " ", summary or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_last_24h() -> list[dict]:
    """Return {title, url, excerpt, date, category} for every Hindu item
    published in the last 24 hours across FEED_SECTIONS."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    items: list[dict] = []
    seen_urls: set[str] = set()

    for feed_url, category in FEED_SECTIONS:
        parsed = feedparser.parse(feed_url, request_headers=HEADERS)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            # Feed didn't parse and returned nothing usable — skip it and
            # let the other feeds still contribute. See README if every
            # feed starts returning nothing.
            continue

        for entry in parsed.entries:
            url = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue

            pub_dt = _parse_pubdate(entry)
            if pub_dt is not None and pub_dt < cutoff:
                continue  # older than our 24h window

            bucket = category
            if AWARD_KEYWORDS.search(title):
                bucket = "awards"

            seen_urls.add(url)
            items.append({
                "title": title,
                "url": url,
                "excerpt": _clean_excerpt(entry.get("summary", "")),
                "date": pub_dt.strftime("%B %d, %Y").replace(" 0", " ") if pub_dt else "",
                "category": bucket,
            })

    return items


if __name__ == "__main__":
    # Quick manual check: python hindu_fetch.py
    items = fetch_last_24h()
    print(f"Fetched {len(items)} item(s) from The Hindu (last {LOOKBACK_HOURS}h)\n")
    for i in items:
        print(f"[{i['category']}] {i['title']} ({i['date']})")
