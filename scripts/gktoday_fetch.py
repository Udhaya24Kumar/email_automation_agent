"""
Fetch current affairs from GKToday, covering the last 24 hours across
pages (GKToday's listing paginates at ~12 posts/page).

GKToday's /current-affairs/ page lists posts in reverse-chronological order,
each already tagged with GKToday's own category (e.g. "Economy & Banking
Current Affairs", "Sports Current Affairs"). We reuse that categorisation
instead of writing our own classifier, and just remap their labels onto the
9 SSC-focused sections.

BUGFIX (Phase 1 -> Phase 2): the original version grouped each post by
walking a title link up to its nearest <div>/<li> ancestor. On GKToday's
actual markup the posts on this page are NOT individually wrapped — many
title headings share the same outer container — so that walk collapsed
every post down to one shared block, and the page returned only a single
article. This version no longer depends on any wrapper element at all: it
walks the page's headings/paragraphs in document order and treats each
h2/h3 post-title as the start of a new item, closing it out when the next
heading (or a "date + category" paragraph) is seen. This is robust to
GKToday changing (or removing) wrapper divs around each post.
"""

import re
import requests
from bs4 import BeautifulSoup

GKTODAY_URL = "https://www.gktoday.in/current-affairs/"
MAX_PAGES = 6  # safety cap; a normal day rarely spans more than 2-3 pages

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
    "User-Agent": "Mozilla/5.0 (compatible; SSC-CA-Digest/0.2; personal study tool)"
}

DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},\s+\d{4}"
)

# Links we should never treat as a post permalink (nav / category / quiz /
# ebook links that happen to sit inside h2/h3 tags on some page layouts).
NON_POST_HREF = re.compile(
    r"/current-affairs/category/|/quizbase/|/gk-questions/|/pdfs/|/hindi/"
)


def _map_category(raw_label: str) -> str:
    label = raw_label.lower()
    for key, bucket in CATEGORY_MAP.items():
        if key in label:
            return bucket
    return "national"


def _page_url(page: int) -> str:
    return GKTODAY_URL if page == 1 else f"{GKTODAY_URL}page/{page}/"


def _parse_page(html: str) -> list[dict]:
    """Parse one listing page into an ordered list of {title, url, excerpt,
    date, category} dicts, without assuming posts are individually wrapped.

    Strategy: walk h2/h3/p tags in document order. Each h2/h3 containing a
    real post link starts a new item; the following <p> tags fill in the
    excerpt (first one) and the "date + category" line (whichever paragraph
    contains both a recognisable date and a category link).
    """
    soup = BeautifulSoup(html, "lxml")
    main = (
        soup.select_one("main")
        or soup.select_one("#main")
        or soup.select_one(".site-content")
        or soup
    )

    items: list[dict] = []
    current: dict | None = None

    def flush():
        nonlocal current
        if current and current.get("title") and current.get("url"):
            items.append(current)
        current = None

    for tag in main.find_all(["h2", "h3", "p"], recursive=True):
        if tag.name in ("h2", "h3"):
            link = tag.find("a", href=True)
            if not link:
                continue
            href = (link.get("href") or "").strip()
            if not href or NON_POST_HREF.search(href):
                continue
            flush()
            current = {
                "title": link.get_text(strip=True),
                "url": href,
                "excerpt": "",
                "date": "",
                "category": "",
            }
        elif tag.name == "p" and current is not None:
            text = tag.get_text(" ", strip=True)
            if not text:
                continue
            date_match = DATE_RE.search(text)
            cat_link = tag.select_one("a[href*='/current-affairs/category/']")
            if date_match or cat_link:
                if date_match and not current["date"]:
                    current["date"] = date_match.group(0)
                if cat_link:
                    current["category"] = _map_category(cat_link.get_text(strip=True))
            elif not current["excerpt"]:
                current["excerpt"] = text

    flush()
    return items


def fetch_today_digest() -> list[dict]:
    """Return every article from the newest date seen on GKToday's
    current-affairs listing, paging through as many listing pages as needed
    (up to MAX_PAGES) so a busy day's full set of stories is captured, not
    just the first ~12 shown on page 1."""
    session = requests.Session()
    session.headers.update(HEADERS)

    all_items: list[dict] = []
    newest_date: str | None = None

    for page in range(1, MAX_PAGES + 1):
        resp = session.get(_page_url(page), timeout=20)
        if resp.status_code != 200:
            break
        page_items = _parse_page(resp.text)
        if not page_items:
            break

        if newest_date is None:
            dated = [i for i in page_items if i["date"]]
            newest_date = dated[0]["date"] if dated else None

        stop = False
        for item in page_items:
            if item["date"] and newest_date and item["date"] != newest_date:
                # Reached the tail of the previous day — the page is
                # reverse-chronological, so everything after this is older.
                stop = True
                break
            item["category"] = item["category"] or "national"
            all_items.append(item)

        if stop:
            break

        # If this page's last item still matches newest_date, there may be
        # more of today's stories on the next page — keep going. If a page
        # returns fewer than ~10 items GKToday probably has no more pages.
        if len(page_items) < 8:
            break

    return all_items


if __name__ == "__main__":
    # Quick manual check: python gktoday_fetch.py
    items = fetch_today_digest()
    print(f"Fetched {len(items)} item(s)\n")
    for i in items:
        print(f"[{i['category']}] {i['title']} ({i['date']})")
