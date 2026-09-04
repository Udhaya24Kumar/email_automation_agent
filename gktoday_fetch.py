"""
Fetch today's current affairs digest from GKToday.

GKToday's /current-affairs/ page lists posts in reverse-chronological order,
each already tagged with GKToday's own category (e.g. "Economy & Banking
Current Affairs", "Sports Current Affairs"). We reuse that categorisation
instead of writing our own classifier, and just remap their labels onto the
9 SSC-focused sections.

The page mixes today's articles with the tail end of the previous day, so we
keep every article that shares the *newest* date seen on the page, and stop
as soon as the date changes.
"""

import re
import requests
from bs4 import BeautifulSoup

GKTODAY_URL = "https://www.gktoday.in/current-affairs/"

# GKToday's own category labels (lowercased, partial match) -> our 9 buckets.
# Anything unmatched falls back to "national" as a safe default.
CATEGORY_MAP = {
    "government schemes": "national",
    "legal": "national",
    "constitution": "national",
    "art & culture": "national",
    "art and culture": "national",
    "places in news": "national",
    "defence": "national",
    "polity": "national",
    "international": "international",
    "world": "international",
    "economy": "economy",
    "banking": "economy",
    "business": "economy",
    "science & technology": "science",
    "science and technology": "science",
    "environment": "environment",
    "biodiversity": "environment",
    "sports": "sports",
    "awards": "awards",
    "honours": "awards",
    "persons in news": "awards",
    "reports": "reports",
    "indices": "reports",
    "indexes": "reports",
    "important days": "important_days",
    "events": "important_days",
}

# (internal key, display heading) — order controls the order in the email
SECTION_ORDER = [
    ("national", "🇮🇳 National Affairs"),
    ("international", "🌍 International Affairs"),
    ("economy", "💰 Economy & Banking"),
    ("science", "🔬 Science & Technology"),
    ("environment", "🌱 Environment"),
    ("sports", "🏆 Sports"),
    ("awards", "🏅 Awards & Appointments"),
    ("reports", "📊 Reports & Indexes"),
    ("important_days", "📅 Important Days"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SSC-CA-Digest/0.1; personal study tool)"
}

DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}"
)


def _map_category(raw_label: str) -> str:
    label = raw_label.lower()
    for key, bucket in CATEGORY_MAP.items():
        if key in label:
            return bucket
    return "national"


def _extract_date(block) -> str:
    text = block.get_text(" ", strip=True)
    match = DATE_RE.search(text)
    return match.group(0) if match else ""


def _fallback_article_blocks(soup):
    """If GKToday isn't using <article> tags when you run this, group each
    title link with its surrounding block by walking up to a stable parent.
    This is a safety net — if it triggers, GKToday's markup has changed and
    you should inspect the page source and adjust the selectors above."""
    blocks = []
    seen = set()
    for h in soup.select("h2 a, h3 a"):
        parent = h.find_parent(["div", "li"])
        if parent is not None and id(parent) not in seen:
            seen.add(id(parent))
            blocks.append(parent)
    return blocks


def fetch_today_digest() -> list[dict]:
    """Return a list of {title, url, excerpt, date, category} for the newest
    batch of articles on GKToday's current-affairs page."""
    resp = requests.get(GKTODAY_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    articles = soup.select("article")
    if not articles:
        articles = _fallback_article_blocks(soup)

    items = []
    newest_date = None

    for art in articles:
        title_tag = art.select_one("h2 a, h3 a")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        url = (title_tag.get("href") or "").strip()
        if not title or not url:
            continue

        excerpt_tag = art.select_one("p")
        excerpt = excerpt_tag.get_text(strip=True) if excerpt_tag else ""

        date_text = _extract_date(art)
        category_tag = art.select_one("a[href*='/current-affairs/category/']")
        category_label = category_tag.get_text(strip=True) if category_tag else ""

        if newest_date is None:
            newest_date = date_text
        elif date_text and date_text != newest_date:
            # Reached yesterday's articles — stop, since the page is
            # reverse-chronological.
            break

        items.append({
            "title": title,
            "url": url,
            "excerpt": excerpt,
            "date": date_text,
            "category": _map_category(category_label),
        })

    return items


if __name__ == "__main__":
    # Quick manual check: python gktoday_fetch.py
    for i in fetch_today_digest():
        print(f"[{i['category']}] {i['title']} ({i['date']})")