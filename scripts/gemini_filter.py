"""
SSC-focused Gemini filtering and enrichment.

Pipeline:
    Raw news
        ↓
    Gemini SSC relevance filtering
        ↓
    Factual summary
        ↓
    SSC keywords
        ↓
    Importance score
        ↓
    Top 30 articles

Gemini is instructed to use ONLY the supplied title/excerpt.
"""

import json
import os
import re
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

MAX_FINAL_ITEMS = 30
BATCH_SIZE = 20
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


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

Ask:

"Could SSC realistically create a General Awareness or Current Affairs
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

IMPORTANT:

Return ONLY articles that have SSC importance 4, or 5.

DO NOT return articles with importance 1 or 2.

For every returned article, include its original input index.

You may return fewer articles than the number of input articles.

Return ONLY a JSON array.

Required format:

[
  {
    "index": 0,
    "title": "Short factual title",
    "summary": "Short factual explanation.",
    "keywords": [
      "Organisation: ...",
      "Scheme: ...",
      "Place: ...",
      "Number: ..."
    ],
    "importance": 5
  }
]

Required format:

[
  {
    "index": 0,
    "title": "Short factual title",
    "summary": "Short factual explanation.",
    "keywords": [
      "Organisation: ...",
      "Scheme: ...",
      "Place: ...",
      "Number: ..."
    ],
    "importance": 5
  }
]

The index MUST match the input index.

Do not include markdown.
Do not include explanations outside JSON.
"""


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

    Never treat unfiltered news as SSC-relevant.
    """

    print(
        "Gemini unavailable — rejecting unfiltered articles."
    )

    return []

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
            indent=2,
        )
    )


def _call_gemini(client, prompt, retries=3):
    """Send one batch to Gemini with retry handling."""

    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )

            text = response.text

            if not text:
                raise ValueError(
                    "Gemini returned an empty response."
                )

            return _extract_json(text)

        except Exception as exc:
            print(
                f"Gemini attempt {attempt}/{retries} failed: {exc}"
            )

            if attempt == retries:
                raise

            wait_seconds = 5 * attempt

            print(
                f"Retrying in {wait_seconds} seconds..."
            )

            time.sleep(wait_seconds)


def _normalise_result(original, result):
    """Safely merge Gemini's result with the original article."""

    if not isinstance(result, dict):
        raise ValueError("Gemini returned an invalid article object.")

    summary = str(
        result.get("summary")
        or original.get("excerpt")
        or original.get("title")
        or ""
    ).strip()

    title = str(
        result.get("title")
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

    Gemini may return only SSC-relevant articles.
    Each returned article must contain its original index.
    """

    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print(
            "GEMINI_API_KEY not set — "
            "skipping AI SSC filtering."
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

        print(
            f"Gemini filtering completed: "
            f"{len(enriched)} SSC candidate(s) "
            f"returned."
        )

        return enriched

    except Exception as exc:
        print(
            f"Gemini filtering failed: {exc}"
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

    dropped = len(items) - len(relevant)

    print(
        f"SSC filtering: "
        f"{len(relevant)} relevant, "
        f"{dropped} rejected."
    )

    return relevant[:MAX_FINAL_ITEMS]


if __name__ == "__main__":
    print(
        "gemini_filter.py is a library module. "
        "Run main.py to execute the complete pipeline."
    )