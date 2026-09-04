"""
Build and send the Sunday weekly PDF summary.

Reads the last 7 days of items that were actually included in a sent daily
digest (data/weekly_items.json, appended to by main.py after each
successful send — see weekly_store.py) and renders them into a single
concise PDF, grouped by SSC section in the same order as the daily email,
then emails it as an attachment via send_mail.send_email_with_attachment().

Run standalone:
    python scripts/weekly_report.py

Wired into .github/workflows/weekly_report.yml, scheduled for Sunday
mornings (after that day's own digest.yml run, so Sunday's items are
already in the store).
"""
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from gktoday_fetch import SECTION_ORDER
from send_mail import send_email_with_attachment
from weekly_store import load_week

# scripts/weekly_report.py -> repo_root/data/...
WEEKLY_PATH = Path(__file__).resolve().parent.parent / "data" / "weekly_items.json"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "weekly_report.pdf"

SECTION_TITLES = dict(SECTION_ORDER)


def _section_label(category: str) -> str:
    return SECTION_TITLES.get(category, "Other Important Affairs")


def _clean(text: str) -> str:
    """fpdf2's built-in core fonts (Helvetica) only support Latin-1, so
    strip emoji/other non-Latin-1 characters rather than let a build
    crash on them. Everything in weekly_items.json is Gemini-phrased
    English by the time it gets here, so this only ever drops decorative
    characters (e.g. the 🇮🇳/📊-style emoji used in section titles).
    """
    return text.encode("latin-1", "ignore").decode("latin-1").strip(" -")


class WeeklyReportPDF(FPDF):
    week_range = ""

    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "SSC Current Affairs -- Weekly Report", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, self.week_range, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def build_pdf(items: list[dict], week_start: str, week_end: str, output_path: Path) -> Path:
    """Render `items` (already the 7-day window from weekly_store.load_week)
    into a concise PDF at `output_path`, grouped by SSC section."""
    pdf = WeeklyReportPDF()
    pdf.week_range = f"{week_start} to {week_end}"
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"{len(items)} item(s) covered this week.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[item.get("category") or "national"].append(item)

    # Same section order as the daily email; anything outside the known
    # 9 buckets is appended at the end rather than dropped.
    ordered_categories = [c for c, _ in SECTION_ORDER if c in grouped]
    ordered_categories += [c for c in grouped if c not in ordered_categories]

    for category in ordered_categories:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_fill_color(230, 230, 230)
        pdf.cell(0, 9, _clean(_section_label(category)), new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(1)

        for item in grouped[category]:
            title = _clean(item.get("title") or "Untitled")
            date_added = item.get("date_added", "")
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, f"- {title} ({date_added})")

            summary = _clean(item.get("summary") or "")
            if summary:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(70, 70, 70)
                pdf.multi_cell(0, 5, summary)
                pdf.set_text_color(0, 0, 0)

            source = item.get("source", "")
            if source:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(120, 120, 120)
                pdf.cell(0, 5, f"Source: {source.title()}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)

            pdf.ln(2)

        pdf.ln(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_path))
    return output_path


def main() -> None:
    items = load_week(WEEKLY_PATH)

    if not items:
        print("No items collected this week -- skipping weekly report.")
        return

    week_start = items[0].get("date_added", "")
    week_end = items[-1].get("date_added", "")

    build_pdf(items, week_start, week_end, OUTPUT_PATH)

    today = datetime.now().strftime("%d %B %Y")
    send_email_with_attachment(
        subject=f"SSC Current Affairs -- Weekly Report ({today})",
        html_body=(
            "<p>Attached is your weekly SSC current-affairs summary, "
            f"covering <strong>{len(items)}</strong> item(s) from "
            f"{week_start} to {week_end}.</p>"
        ),
        attachment_path=OUTPUT_PATH,
        attachment_name="SSC_Weekly_Report.pdf",
    )

    print(f"Weekly report sent with {len(items)} item(s) covering {week_start} to {week_end}.")


if __name__ == "__main__":
    main()
