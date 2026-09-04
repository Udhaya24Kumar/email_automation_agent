"""
Fetch today's press releases from PIB (Press Information Bureau) for
fact-grounding — PIB is the primary-source government release, so it's the
thing to cross-check GKToday/Hindu's phrasing against.

IMPORTANT — read this before debugging silently-empty output:
PIB's https://www.pib.gov.in/allRel.aspx is an ASP.NET WebForms page whose
language toggle (Hindi/English) and ministry/date filters are all done via
JS postbacks (__VIEWSTATE/__EVENTTARGET), not URL query params. Confirmed
by hand: requesting the page with ?lang=1&reg=1 still returns Hindi content
(it silently redirects to lang=2&reg=48 regardless of the query string).
There is no plain-HTTP way to force the English view without either
replaying the postback (fragile — the VIEWSTATE token is regenerated per
request) or driving a real browser (Playwright/Selenium — heavier than this
project wants to depend on for one source).

So: this fetcher deliberately takes the Hindi default view, which — useful
detail — already defaults to *today's date* with no filtering needed. We
categorise by matching the Hindi ministry heading against MINISTRY_MAP
below (built from PIB's own ministry dropdown labels), and leave the Hindi
title as-is. gemini_filter.py is responsible for translating + phrasing it
into an SSC-ready English one-liner — translation is a mechanical transform
of the given text, not new information, so it stays within "grounded
strictly in scraped text".

If PIB ever adds a working lang= query param (worth re-testing occasionally
since gov sites do get rebuilt), delete the Hindi-detection path below and
this gets much simpler.
"""

import re
import requests
from bs4 import BeautifulSoup

PIB_ALL_RELEASES_URL = "https://www.pib.gov.in/allRel.aspx"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SSC-CA-Digest/0.2; personal study tool)"
}

# Hindi ministry heading (as it appears on PIB's page) -> our 9 buckets.
MINISTRY_MAP = {
    "प्रधानमंत्री कार्यालय": "national",           # PMO
    "गृह मंत्रालय": "national",                     # Home Affairs
    "विधि एवं न्‍याय": "national",                   # Law & Justice
    "संस्‍कृति मंत्रालय": "national",                 # Culture
    "रक्षा मंत्रालय": "national",                    # Defence
    "पंचायती राज": "national",
    "सामाजिक न्‍याय": "national",                    # Social Justice
    "महिला एवं बाल विकास": "national",                # Women & Child Dev
    "जनजातीय कार्य": "national",                     # Tribal Affairs
    "आवासन और शहरी": "national",                     # Housing & Urban
    "ग्रामीण विकास": "national",                      # Rural Development
    "अल्‍पसंख्‍यक": "national",                       # Minority Affairs
    "विदेश मंत्रालय": "international",               # External Affairs
    "वाणिज्‍य एवं उद्योग": "economy",                 # Commerce & Industry
    "वित्‍त मंत्रालय": "economy",                     # Finance
    "कॉरपोरेट कार्य": "economy",                      # Corporate Affairs
    "सहकारिता मंत्रालय": "economy",                   # Cooperation
    "श्रम और रोजगार": "economy",                      # Labour & Employment
    "उद्यमिता मंत्रालय": "economy",                   # Skill Dev / Entrepreneurship
    "इलेक्ट्रानिक्स एवं आईटी": "science",             # Electronics & IT
    "विज्ञान एवं प्रौद्योगिकी": "science",             # Science & Tech
    "अंतरिक्ष विभाग": "science",                      # Dept of Space
    "अणु ऊर्जा विभाग": "science",                     # Atomic Energy
    "पृथ्‍वी विज्ञान": "science",                      # Earth Sciences
    "पर्यावरण, वन एवं जलवायु": "environment",          # Environment, Forest & Climate
    "जल शक्ति मंत्रालय": "environment",                # Jal Shakti
    "नवीन एवं नवीकरणीय ऊर्जा": "environment",           # New & Renewable Energy
    "युवा कार्यक्रम एवं खेल": "sports",                # Youth Affairs & Sports
    "सांख्यिकी एवं कार्यक्रम कार्यान्‍वयन": "reports",  # Statistics & Programme Implementation
}

RELEASE_LINK_RE = re.compile(r"PressReleaseDetail\.aspx\?PRID=\d+", re.IGNORECASE)

# Rough heuristic: PIB headings/titles on the Hindi default view are
# Devanagari script. If we ever *do* get English back (e.g. PIB fixes the
# lang param), this simply won't match and items pass through unchanged.
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _map_ministry(heading_text: str) -> str:
    for key, bucket in MINISTRY_MAP.items():
        if key in heading_text:
            return bucket
    return "national"


def fetch_today_releases() -> list[dict]:
    """Return {title, url, excerpt, date, category, lang} for today's PIB
    press releases, grouped by ministry. `lang` is 'hi' or 'en' so
    downstream code knows whether translation is needed. Returns an empty
    list if PIB's markup no longer matches — see the module docstring."""
    resp = requests.get(PIB_ALL_RELEASES_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    items: list[dict] = []
    current_ministry = ""

    # PIB groups releases under "### Ministry Name" headings followed by a
    # bullet list of release links — walk h3/a in document order the same
    # defensive way as gktoday_fetch, rather than trusting a specific
    # wrapper class that PIB could rename.
    content = soup.select_one("#pageContent") or soup

    for tag in content.find_all(["h3", "a"], recursive=True):
        if tag.name == "h3":
            text = tag.get_text(strip=True)
            if text:
                current_ministry = text
            continue

        href = (tag.get("href") or "").strip()
        if not RELEASE_LINK_RE.search(href):
            continue
        title = tag.get_text(strip=True)
        if not title:
            continue

        items.append({
            "title": title,
            "url": href if href.startswith("http") else f"https://www.pib.gov.in/{href.lstrip('/')}",
            "excerpt": "",
            "date": "",  # PIB's default view is already "today" — no per-item date shown
            "category": _map_ministry(current_ministry),
            "lang": "hi" if DEVANAGARI_RE.search(title) else "en",
        })

    return items


if __name__ == "__main__":
    # Quick manual check: python pib_fetch.py
    items = fetch_today_releases()
    if not items:
        print("No releases parsed — inspect", PIB_ALL_RELEASES_URL)
        print("(see this file's docstring: PIB's filters are JS postbacks,")
        print("so this only ever sees the default Hindi/today view).")
    for i in items:
        print(f"[{i['category']}] ({i['lang']}) {i['title']}")
