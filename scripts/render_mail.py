
"""
Render the SSC Current Affairs email.

The email is designed for quick SSC CGL revision:

Category
    ↓
Important news
    ↓
Short factual explanation
    ↓
SSC Keywords
    ↓
Source

Only selected/relevant articles should reach this renderer.
"""

from html import escape

from gktoday_fetch import SECTION_ORDER


MAX_KEYWORDS_PER_ITEM = 6


def _safe(value) -> str:
    return escape(str(value or ""))


def _get_section_title(category: str) -> str:
    for key, title in SECTION_ORDER:
        if key == category:
            return title

    return "📰 Other Important Affairs"


def _source_name(source: str) -> str:
    names = {
        "gktoday": "GKToday",
        "hindu": "The Hindu",
        "pib": "PIB",
    }

    return names.get(source, source.title() if source else "Source")


def _render_keywords(keywords) -> str:
    if not keywords:
        return ""

    keyword_items = []

    for keyword in keywords[:MAX_KEYWORDS_PER_ITEM]:
        keyword_items.append(
            f"""
            <li style="
                margin-bottom:6px;
                color:#333333;
                font-size:14px;
                line-height:1.5;
            ">
                {_safe(keyword)}
            </li>
            """
        )

    return f"""
    <div style="
        margin-top:14px;
        padding:12px 14px;
        background:#f7f7f7;
        border-left:4px solid #555555;
        border-radius:4px;
    ">
        <div style="
            font-weight:700;
            font-size:13px;
            letter-spacing:0.4px;
            margin-bottom:7px;
            color:#333333;
        ">
            📌 SSC KEYWORDS
        </div>

        <ul style="
            margin:0;
            padding-left:20px;
        ">
            {''.join(keyword_items)}
        </ul>
    </div>
    """


def _render_item(item: dict, number: int) -> str:
    title = _safe(
        item.get("title")
        or item.get("summary")
        or "Important Current Affair"
    )

    summary = _safe(
        item.get("summary")
        or item.get("excerpt")
        or item.get("title")
        or ""
    )

    source = _source_name(item.get("source", ""))

    url = item.get("url", "")

    importance = item.get("importance", 3)

    if importance >= 5:
        importance_label = "⭐ Very Important"
    elif importance >= 4:
        importance_label = "🔥 High Priority"
    else:
        importance_label = "✓ Important"

    source_link = ""

    if url:
        source_link = f"""
        <a
            href="{_safe(url)}"
            style="
                color:#1565c0;
                text-decoration:none;
                font-size:13px;
                font-weight:600;
            "
        >
            Read Source →
        </a>
        """

    keywords_html = _render_keywords(
        item.get("keywords", [])
    )

    return f"""
    <div style="
        background:#ffffff;
        border:1px solid #e0e0e0;
        border-radius:8px;
        padding:18px;
        margin-bottom:16px;
    ">

        <div style="
            font-size:12px;
            color:#666666;
            margin-bottom:7px;
        ">
            {importance_label} &nbsp;•&nbsp; {_safe(source)}
        </div>

        <div style="
            font-size:18px;
            line-height:1.4;
            font-weight:700;
            color:#222222;
            margin-bottom:10px;
        ">
            {number}. {title}
        </div>

        <div style="
            font-size:14px;
            line-height:1.65;
            color:#444444;
        ">
            {summary}
        </div>

        {keywords_html}

        <div style="
            margin-top:14px;
        ">
            {source_link}
        </div>

    </div>
    """


def _render_section(title: str, items: list[dict]) -> str:
    if not items:
        return ""

    rendered_items = []

    for index, item in enumerate(items, start=1):
        rendered_items.append(
            _render_item(item, index)
        )

    return f"""
    <div style="margin-bottom:30px;">

        <div style="
            font-size:21px;
            font-weight:800;
            color:#222222;
            padding-bottom:9px;
            margin-bottom:14px;
            border-bottom:2px solid #222222;
        ">
            {_safe(title)}
        </div>

        {''.join(rendered_items)}

    </div>
    """


def build_html(
    items: list[dict],
    quiz: list[dict],
    today: str,
) -> str:
    """
    Build the complete HTML email.

    News is grouped according to SECTION_ORDER.

    Quiz questions are displayed after the current affairs section.
    """

    sections = []

    # Group news by category.
    grouped = {}

    for item in items:
        category = item.get("category", "national")
        grouped.setdefault(category, []).append(item)

    # Render sections in predefined SSC order.
    for category, title in SECTION_ORDER:
        category_items = grouped.get(category, [])

        if category_items:
            sections.append(
                _render_section(title, category_items)
            )

    # Handle unexpected categories without losing them.
    known_categories = {
        category
        for category, _ in SECTION_ORDER
    }

    unknown_items = [
        item
        for item in items
        if item.get("category", "national")
        not in known_categories
    ]

    if unknown_items:
        sections.append(
            _render_section(
                "📰 Other Important Affairs",
                unknown_items,
            )
        )

    news_html = "".join(sections)

    quiz_html = _render_quiz(quiz)

    total_news = len(items)
    total_quiz = len(quiz)

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SSC Current Affairs</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#f2f2f2;
    font-family:Arial, Helvetica, sans-serif;
">

<div style="
    max-width:760px;
    margin:0 auto;
    padding:20px 12px 40px 12px;
">

    <!-- HEADER -->

    <div style="
        background:#222222;
        color:#ffffff;
        padding:24px 20px;
        border-radius:9px;
        margin-bottom:22px;
    ">

        <div style="
            font-size:25px;
            font-weight:800;
            margin-bottom:7px;
        ">
            🇮🇳 SSC Daily Current Affairs
        </div>

        <div style="
            font-size:14px;
            opacity:0.9;
        ">
            {_safe(today)}
        </div>

        <div style="
            margin-top:14px;
            font-size:13px;
            line-height:1.5;
            opacity:0.85;
        ">
            SSC-focused news • Important facts • Exam keywords
        </div>

    </div>


    <!-- SUMMARY -->

    <div style="
        background:#ffffff;
        border:1px solid #dddddd;
        border-radius:8px;
        padding:15px 18px;
        margin-bottom:25px;
        font-size:14px;
        color:#444444;
    ">

        <strong>{total_news}</strong> important current-affairs item(s)

        &nbsp;•&nbsp;

        <strong>{total_quiz}</strong> GKToday quiz question(s)

    </div>


    <!-- CURRENT AFFAIRS -->

    {news_html}


    <!-- QUIZ -->

    {quiz_html}


    <!-- FOOTER -->

    <div style="
        border-top:1px solid #dddddd;
        margin-top:25px;
        padding-top:18px;
        text-align:center;
        color:#777777;
        font-size:12px;
        line-height:1.5;
    ">

        SSC Current Affairs Daily Digest

        <br>

        Automatically generated for exam preparation.

    </div>

</div>

</body>
</html>
"""


def _render_quiz(quiz: list[dict]) -> str:
    if not quiz:
        return ""

    question_blocks = []

    for index, question in enumerate(quiz, start=1):

        question_text = _safe(
            question.get("question", "")
        )

        options = question.get("options", [])

        option_html = []

        for option in options:
            option_html.append(
                f"""
                <li style="
                    margin-bottom:5px;
                    font-size:14px;
                    line-height:1.5;
                ">
                    {_safe(option)}
                </li>
                """
            )

        answer = _safe(
            question.get("answer")
            or question.get("correct_answer")
            or ""
        )

        explanation = _safe(
            question.get("notes")
            or question.get("explanation")
            or ""
        )

        explanation_html = ""

        if explanation:
            explanation_html = f"""
            <div style="
                margin-top:8px;
                color:#555555;
                font-size:13px;
                line-height:1.5;
            ">
                <strong>Why:</strong> {explanation}
            </div>
            """

        question_blocks.append(
            f"""
            <div style="
                background:#ffffff;
                border:1px solid #e0e0e0;
                border-radius:8px;
                padding:16px;
                margin-bottom:12px;
            ">

                <div style="
                    font-size:15px;
                    line-height:1.5;
                    font-weight:700;
                    margin-bottom:9px;
                ">
                    {index}. {question_text}
                </div>

                <ol style="
                    margin:0;
                    padding-left:22px;
                ">
                    {''.join(option_html)}
                </ol>

                <div style="
                    margin-top:10px;
                    padding:9px 11px;
                    background:#f7f7f7;
                    font-size:13px;
                ">
                    <strong>Correct Answer:</strong> {answer}
                </div>

                {explanation_html}

            </div>
            """
        )

    return f"""
    <div style="
        margin-top:35px;
    ">

        <div style="
            font-size:21px;
            font-weight:800;
            color:#222222;
            padding-bottom:9px;
            margin-bottom:14px;
            border-bottom:2px solid #222222;
        ">
            📝 Daily Current Affairs Quiz
        </div>

        {''.join(question_blocks)}

    </div>
    """
