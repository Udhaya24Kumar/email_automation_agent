"""
Fetch today's daily current affairs MCQ quiz from GKToday.

GKToday publishes one "Daily Current Affairs Quiz" post per day, listed on
the quiz index page and linked as a post whose URL slug contains
`daily-current-affairs-quiz-`. We take the newest such link, then parse the
individual question blocks out of the post body.

The question markup on GKToday's quiz posts follows a consistent text
pattern per question:

    <question text>
    [A] <option>
    [B] <option>
    [C] <option>
    [D] <option>
    Correct Answer: <letter/text>
    Notes: <explanation>            (not always present)

We rely on that `[A] ... [B] ... [C] ... [D] ... Correct Answer:` shape
rather than any specific CSS class, since GKToday's HTML wrapper around the
questions has changed before. If GKToday changes the *text* pattern itself,
this will return an empty list — see README's "If it stops working" section.
"""

import re
import requests
from bs4 import BeautifulSoup

QUIZ_INDEX_URL = "https://www.gktoday.in/gk-current-affairs-quiz-questions-answers/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SSC-CA-Digest/0.1; personal study tool)"
}

QUIZ_LINK_RE = re.compile(r"daily-current-affairs-quiz-", re.IGNORECASE)

# Splits the post body text into per-question chunks. Each chunk starts at
# a line that isn't itself an [A]/[B]/[C]/[D]/Correct Answer/Notes line —
# i.e. the question stem — up to (but not including) the next such stem.
OPTION_RE = re.compile(r"^\[([A-D])\]\s*(.+)$")
ANSWER_RE = re.compile(r"^Correct\s+Answer:?\s*\[?([A-D])\]?\.?\s*(.*)$", re.IGNORECASE)
NOTES_RE = re.compile(r"^Notes?:?\s*(.*)$", re.IGNORECASE)


def _find_latest_quiz_url() -> str | None:
    resp = requests.get(QUIZ_INDEX_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    for a in soup.select("h2 a, h3 a, article a"):
        href = a.get("href") or ""
        if QUIZ_LINK_RE.search(href):
            return href
    return None


def _parse_questions(post_text_lines: list[str]) -> list[dict]:
    questions = []
    current = None

    for raw_line in post_text_lines:
        line = raw_line.strip()
        if not line:
            continue

        opt_match = OPTION_RE.match(line)
        ans_match = ANSWER_RE.match(line)
        notes_match = NOTES_RE.match(line)

        if ans_match:
            if current is not None:
                letter = ans_match.group(1).upper()
                current["correct_letter"] = letter
                trailing = ans_match.group(2).strip()
                if trailing:
                    current["correct_text"] = trailing
            continue

        if notes_match:
            if current is not None:
                current["explanation"] = notes_match.group(1).strip()
            continue

        if opt_match:
            if current is not None:
                letter, text = opt_match.group(1), opt_match.group(2).strip()
                current["options"][letter] = text
            continue

        # Not an option/answer/notes line -> treat as (start of) a question
        # stem. If we don't have an in-progress question yet, or the current
        # one already has all 4 options + an answer, this starts a new one.
        if current is None or (len(current["options"]) >= 4 and current.get("correct_letter")):
            if current is not None and current["options"] and current.get("correct_letter"):
                questions.append(current)
            current = {"question": line, "options": {}, "correct_letter": None,
                       "correct_text": "", "explanation": ""}
        else:
            # Continuation of a multi-line question stem.
            current["question"] = (current["question"] + " " + line).strip()

    if current is not None and current["options"] and current.get("correct_letter"):
        questions.append(current)

    # Fill in correct_text from the matching option letter if not already
    # captured directly after "Correct Answer:".
    cleaned = []
    for q in questions:
        if not q.get("correct_text") and q.get("correct_letter") in q["options"]:
            q["correct_text"] = q["options"][q["correct_letter"]]
        if len(q["options"]) >= 2 and q.get("correct_letter"):
            cleaned.append(q)
    return cleaned


def fetch_today_quiz() -> list[dict]:
    """Return a list of {question, options, correct_letter, correct_text,
    explanation} for today's GKToday daily current affairs quiz. Returns an
    empty list if no quiz post is found or the text pattern doesn't match."""
    quiz_url = _find_latest_quiz_url()
    if not quiz_url:
        return []

    resp = requests.get(quiz_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    body = soup.select_one("article") or soup.select_one(".entry-content") or soup
    # get_text with a separator that preserves line breaks between block
    # elements (<p>, <br>, <li>, etc.) so the [A]/[B]/[C]/[D]/Correct Answer
    # pattern lines up one-per-line the way it's authored on the page.
    text = body.get_text("\n", strip=True)
    lines = text.split("\n")

    return _parse_questions(lines)


if __name__ == "__main__":
    # Quick manual check: python gktoday_quiz.py
    qs = fetch_today_quiz()
    if not qs:
        print("No quiz questions parsed — inspect", QUIZ_INDEX_URL)
    for i, q in enumerate(qs, 1):
        print(f"{i}. {q['question']}")
        for letter, text in q["options"].items():
            marker = " <-- correct" if letter == q["correct_letter"] else ""
            print(f"   [{letter}] {text}{marker}")
        if q["explanation"]:
            print(f"   Notes: {q['explanation']}")
        print()
