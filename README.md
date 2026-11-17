# SSC Current Affairs Digest

The daily job fetches GKToday, The Hindu, and PIB, merges similar stories,
ranks them for SSC with Gemini, and emails the selected source headlines,
excerpts, and links. It also includes GKToday's quiz. Sunday’s scheduled run
builds and sends a weekly PDF after the daily job saves its delivery history.

Gemini can select and score articles. The email retains source wording,
including Hindi from PIB. If Gemini is unavailable, the news fallback is
limited to original PIB releases. Use the source links to verify coverage.

## GitHub Actions setup

Add repository secrets named `GMAIL_USER`, `GMAIL_APP_PASSWORD`, and
`TO_EMAIL`. Gmail requires an App Password. Add `GEMINI_API_KEY` for SSC
ranking. You can set a repository variable named `GEMINI_MODEL` to override
the Python default of `gemini-3.6-flash`.

The daily job runs at 06:30 IST and can also be triggered manually. It
requires permission to push the delivery history in `data/` back to the
branch. The weekly workflow can be triggered manually from Actions.

## Preview locally

Install the dependencies with `python -m pip install -r requirements.txt`.
Run these commands from the repository root:

```sh
python scripts/main.py --preview preview/digest.html
python scripts/weekly_report.py --preview preview/weekly.pdf
python -m unittest discover -s tests
```

The daily preview can fetch live feeds and use Gemini if the key is set.
Both previews skip SMTP and leave delivery history alone. The PDF uses
Noto Sans and Noto Sans Devanagari on Linux (`fonts-noto-core` on Ubuntu).
On Windows it uses Arial for Latin text. Set `PDF_FONT_DIR` to the directory
holding `NotoSansDevanagari-Regular.ttf` if it is elsewhere.

## Troubleshooting

- The daily job logs source failures and continues with available sources.
- The weekly job renders the PDF and sends it in separate Actions steps.
  It skips delivery when there are no recorded articles in the IST week.
- If email delivery succeeds but saving or pushing history fails, verify
  delivery before rerunning. SMTP and Git cannot commit together.
