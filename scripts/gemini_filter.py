"""
Enrich articles with SSC CGL relevance using Gemini API.

Takes merged/deduplicated articles and:
1. Filters for SSC CGL exam usefulness
2. Rewrites titles/summaries in exam-friendly language
3. Extracts exam keywords
4. Assigns importance (1-5)

Falls back gracefully if Gemini unavailable.
"""

import json
import os
import re

import google.genai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
BATCH_SIZE = 20
MAX_FINAL_ITEMS = 30

SYSTEM_INSTRUCTION = """
You are an expert SSC CGL current-affairs editor.

Your job is to identify ONLY current-affairs news that is genuinely
useful for SSC CGL General Awareness and Current Affairs preparation.

DO NOT summarize every article.

KEEP articles related to:

1. Indian Polity and Constitution
2. Government schemes and programmes
3. Important government decisions
4. Parliament and major legislation
5. Supreme Court / High Court judgments with national importance
6. Economy, banking, RBI, SEBI, GDP, inflation and taxation
7. Union Budget and major economic policies
8. Defence and military exercises
9. Missiles, weapons and defence agreements
10. ISRO and important space missions
11. Important scientific discoveries
12. Science and Technology
13. Environment, climate and biodiversity
14. International relations
15. UN and international organisations
16. Important international agreements
17. Major international summits and conferences
18. Reports, indexes and rankings
19. Important statistics
20. Awards and honours
21. Important appointments
22. Important personalities
23. Major sports achievements, records and championships
24. Important days and themes
25. Books and authors
26. Major national or international events with clear GK value

REJECT:

- Local crime
- Murders
- Individual arrests
- Accidents
- Routine police news
- Local political accusations
- Political statements without important policy implications
- Editorials
- Opinion articles
- Human-interest stories
- Local civic problems
- Local infrastructure news without national importance
- Entertainment news
- Celebrity news
- Lifestyle news
- Restaurant/culture/travel news
- Routine company/business news
- Routine sports match reports
- Minor local events
- Duplicate stories
- News without useful factual GK information

SSC VALUE TEST:

Ask: "Could SSC realistically create a General Awareness or Current Affairs
question from the facts in this article?"

If NO → importance 1 or 2.
If YES → importance 3, 4 or 5.

IMPORTANT:

Use ONLY the supplied title and excerpt.
DO NOT use outside knowledge.
DO NOT invent facts.
DO NOT add facts from memory.
DO NOT assume missing information.

Every keyword must be directly supported by the supplied text.

For each article:

1. Decide its SSC importance.
2. Create a concise factual title.
3. Create a 1–2 sentence factual summary.
4. Extract 3–6 important SSC keywords/facts.
5. Assign importance from 1 to 5.

Importance:

5 = Extremely important / very likely exam value
4 = Highly useful for SSC
3 = Useful for SSC
2 = Low value
1 = Reject

ONLY scores 3, 4 and 5 should ultimately be included.

For Hindi content, translate into clear English without adding facts.

Return ONLY a JSON array.

IMPORTANT: Return ONLY articles that have SSC importance 4 or 5.

DO NOT return articles with importance 1, 2 or 3.

For every returned article, include its original input index.
"""


def _extract_ssc_keywords(title: str, excerpt: str) -> list[str]:
    """
    Extract SSC-exam-focused keywords from title and excerpt.
    
    Looks for:
    - Proper nouns (organisations, places, people names)
    - Key numbers/percentages
    - Important schemes/programmes
    - Government bodies
    - Acronyms
    """
    text = (title or "") + " " + (excerpt or "")
    
    # Common words to skip
    skip_words = {
        "the", "a", "an", "and", "or", "but", "is", "was", "are",
        "be", "been", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "must",
        "can", "of", "to", "in", "on", "at", "by", "for", "with",
        "from", "as", "said", "says", "told", "new", "old", "more",
        "india", "indian", "country", "year", "time", "news", "report",
    }
    
    keywords = []
    seen = set()
    
    # Pattern 1: Capitalized words (proper nouns)
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
    for word in words:
        if word.lower() not in skip_words and len(word) > 2:
            if word.lower() not in seen:
                keywords.append(word)
                seen.add(word.lower())
    
    # Pattern 2: ALL CAPS (acronyms like SEBI, RBI, ISRO)
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
    for acronym in acronyms:
        if acronym.lower() not in skip_words and len(acronym) >= 2:
            if acronym not in seen:
                keywords.append(acronym)
                seen.add(acronym.lower())
    
    # Pattern 3: Numbers with % (percentages, rates)
    percentages = re.findall(r'[\d.]+\s*%', text)
    for pct in percentages:
        if pct not in seen:
            keywords.append(pct.strip())
            seen.add(pct.lower())
    
    # Pattern 4: Numbers with currency/units
    numbers = re.findall(r'₹[\d,.]+ (?:crore|lakh|billion|million|trillion)?', text, re.IGNORECASE)
    for num in numbers:
        if num not in seen:
            keywords.append(num.strip())
            seen.add(num.lower())
    
    return list(keywords)[:6]  # Cap at 6 keywords


def _extract_json(text: str):
    """Extract a JSON array from Gemini's response."""

    if not text:
        raise ValueError("Gemini returned empty response.")

    text = text.strip()

    # Remove markdown fences if Gemini adds them.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    start = text.find("[")
    end = text.rfind("]")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini did not return a JSON array.")

    return json.loads(text[start:end + 1])


def _fallback(items):
    """
    Safe fallback if Gemini is unavailable.

    Keeps all items with auto-extracted SSC keywords and importance=3
    (fails OPEN: better to include borderline items than to blank the digest).
    """

    print(
        f"Gemini unavailable — keeping all {len(items)} unfiltered "
        "article(s) with auto-extracted keywords (fails open)."
    )

    return [
        {
            **item,
            "title": item.get("title", ""),
            "summary": item.get("excerpt") or item.get("title", ""),
            "keywords": _extract_ssc_keywords(
                item.get("title", ""),
                item.get("excerpt", "")
            ),
            "importance": 3,
            "relevance": "medium",
        }
        for item in items
    ]


def _build_batch_prompt(items, start_index):
    """Build a small Gemini request."""

    payload = []

    for offset, item in enumerate(items):
        payload.append(
            {
                "index": start_index + offset,
                "title": item.get("title", ""),
                "excerpt": item.get("excerpt", ""),
                "category": item.get("category", ""),
                "source": item.get("source", ""),
            }
        )

    return (
        SYSTEM_INSTRUCTION
        + "\n\nINPUT ARTICLES:\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
        )
    )


def _call_gemini(client, prompt):
    """Make a Gemini API call with retry logic."""

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            return _extract_json(response.text)

        except Exception as exc:
            print(
                f"Gemini attempt {attempt}/{max_attempts} failed: {exc}"
            )

            if attempt < max_attempts:
                import time
                wait = min(10, 5 * attempt)
                print(f"Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                raise

    raise Exception("Gemini failed after max retries")


def _normalise_result(original, result):
    """Convert Gemini's response into our internal format."""

    title = (
        result.get("title")
        or original.get("title")
        or ""
    ).strip()

    summary = (
        result.get("summary")
        or original.get("excerpt")
        or original.get("title")
        or ""
    ).strip()

    keywords = result.get("keywords", [])

    if not isinstance(keywords, list):
        keywords = []

    keywords = [
        str(keyword).strip()
        for keyword in keywords
        if str(keyword).strip()
    ][:6]

    try:
        importance = int(result.get("importance", 1))
    except (TypeError, ValueError):
        importance = 1

    importance = max(1, min(5, importance))

    if importance >= 4:
        relevance = "high"
    elif importance == 3:
        relevance = "medium"
    else:
        relevance = "low"

    return {
        **original,
        "title": title,
        "summary": summary,
        "keywords": keywords,
        "importance": importance,
        "relevance": relevance,
    }


def enrich_items(items):
    """
    Process news through Gemini in batches.

    Preserves partial results: if batch N fails, batches 1...N-1 still
    go through enrichment. Only failed batches fall back to auto-keywords.
    """

    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print(
            "GEMINI_API_KEY not set — "
            "skipping AI SSC filtering, using auto-keywords."
        )
        return _fallback(items)

    print(
        f"Gemini SSC filtering started: "
        f"{len(items)} article(s), "
        f"batch size={BATCH_SIZE}, "
        f"model={GEMINI_MODEL}"
    )

    try:
        client = genai.Client(api_key=api_key)

        enriched = []
        failed_batches = []

        total_batches = (
            len(items) + BATCH_SIZE - 1
        ) // BATCH_SIZE

        for batch_number, start in enumerate(
            range(0, len(items), BATCH_SIZE),
            start=1,
        ):
            batch = items[start:start + BATCH_SIZE]

            print(
                f"Gemini batch "
                f"{batch_number}/{total_batches}: "
                f"{len(batch)} article(s)"
            )

            try:
                prompt = _build_batch_prompt(
                    batch,
                    start,
                )

                results = _call_gemini(
                    client,
                    prompt,
                )

                if not isinstance(results, list):
                    raise ValueError(
                        "Gemini response is not a JSON array."
                    )

                print(
                    f"Gemini batch {batch_number}: "
                    f"{len(batch)} input → "
                    f"{len(results)} SSC candidate(s)"
                )

                for result in results:

                    if not isinstance(result, dict):
                        print(
                            "Skipping invalid Gemini result."
                        )
                        continue

                    returned_index = result.get("index")

                    try:
                        returned_index = int(returned_index)
                    except (TypeError, ValueError):
                        print(
                            "Skipping Gemini result with "
                            "invalid index."
                        )
                        continue

                    if (
                        returned_index < start
                        or returned_index >= start + len(batch)
                    ):
                        print(
                            f"Skipping Gemini result with "
                            f"out-of-range index "
                            f"{returned_index}."
                        )
                        continue

                    original = items[returned_index]

                    enriched.append(
                        _normalise_result(
                            original,
                            result,
                        )
                    )

            except Exception as batch_exc:
                print(
                    f"Gemini batch {batch_number} failed: {batch_exc}. "
                    f"Falling back for this batch only."
                )
                failed_batches.append(batch)

        print(
            f"Gemini filtering completed: "
            f"{len(enriched)} SSC candidate(s) "
            f"from successful batch(es)."
        )

        # Fallback only for failed batches, preserving successful ones
        fallback_items = []
        for batch in failed_batches:
            fallback_items.extend(batch)

        if fallback_items:
            print(
                f"Falling back for {len(fallback_items)} "
                f"item(s) from failed batch(es)."
            )
            enriched.extend(_fallback(fallback_items))

        return enriched

    except Exception as exc:
        print(
            f"Gemini filtering failed catastrophically: {exc}"
        )

        print(
            "Falling back to original articles."
        )

        return _fallback(items)


def filter_low_relevance(items):
    """
    Keep only SSC-relevant articles.

    5 = extremely important
    4 = high priority
    3 = useful
    2/1 = rejected

    Maximum 30 articles.
    """

    relevant = [
        item
        for item in items
        if item.get("importance", 1) >= 3
    ]

    # Highest importance first.
    relevant.sort(
        key=lambda item: (
            item.get("importance", 1),
            len(item.get("keywords", [])),
        ),
        reverse=True,
    )

    print(
        f"SSC filtering: {len(relevant)} relevant, "
        f"{len(items) - len(relevant)} rejected."
    )

    return relevant[:MAX_FINAL_ITEMS]
