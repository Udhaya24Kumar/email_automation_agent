# SSC Current Affairs Digest

Pulls the last 24 hours of current affairs from **three sources**
(GKToday, The Hindu, PIB), cross-checks and merges them, filters out
anything sent in the last 5 days, uses **Gemini** to score SSC-relevance
and phrase each item as an exam-ready one-liner (grounded strictly in the
scraped text — never the model's own knowledge), and emails you an HTML
digest grouped into your 9 sections, plus GKToday's daily MCQ quiz.

**Phase 2**: three sources + Gemini relevance filtering/phrasing.
**Phase 1** (dedup + real MCQs) is still all in here too.

Also included: a **weekly PDF report**, auto-generated and emailed every
Sunday, summarizing everything sent in the daily digests that week.

## What changed from Phase 1 → Phase 2

- **Bug fix**: `gktoday_fetch.py` was only ever returning one article. The
  old code grouped each post by walking its title link up to the nearest
  wrapping `<div>`/`<li>` — but GKToday's posts on that page aren't
  individually wrapped, so every post collapsed into the same block. It's
  been rewritten to walk headings/paragraphs in document order instead
  (no wrapper assumption), and now also pages through GKToday's listing
  (`/current-affairs/page/2/`, etc.) so a busy day's full set of stories is
  captured, not just the first ~12.
- **`hindu_fetch.py`** (new) — pulls The Hindu's public RSS feeds
  (national, international, economy, science, environment, sports),
  keeping only items published in the last 24 hours.
- **`pib_fetch.py`** (new) — scrapes PIB's official press-release listing
  for fact-grounding. **Read the caveat below before relying on this one.**
- **`merge_sources.py`** (new) — combines all three sources, tags each item
  with where it came from, and collapses cross-source duplicates (the same
  story reported by more than one outlet) using the same fuzzy-title
  matching as the historical dedup.
- **`gemini_filter.py`** (new) — one batched Gemini call per run scores
  each item's SSC-relevance (high/medium/low) and writes a one-liner,
  translating PIB's Hindi titles in the process. Strictly grounded: the
  prompt forbids adding facts not present in the scraped title/excerpt.
  Low-relevance items are dropped from the email. **Fails open** — if
  `GEMINI_API_KEY` isn't set or the call errors, every item is kept as-is
  with its original (untranslated) title, so a broken AI step degrades the
  digest instead of blanking it.

## ⚠️ About the PIB source

PIB's press-release listing (`pib.gov.in/allRel.aspx`) is an ASP.NET
WebForms page. Its language toggle and date/ministry filters are all done
via JS postbacks, not URL parameters — confirmed by testing directly:
requesting the page with `?lang=1&reg=1` still comes back in Hindi. There's
no reliable plain-HTTP way to force the English view short of replaying the
postback (fragile — the token regenerates per request) or running a real
browser.

So `pib_fetch.py` deliberately takes the Hindi default view — which, useful
detail, already defaults to *today's* releases with no filtering needed —
categorises by matching the Hindi ministry heading, and leaves translation
to the Gemini step. If PIB ever ships a working `lang=` parameter (worth
re-testing occasionally), this can be simplified a lot; see the comment at
the top of `pib_fetch.py`.

## Setup

1. **Create a Gmail App Password**
   - Turn on 2-Step Verification: https://myaccount.google.com/security
   - Generate an App Password: https://myaccount.google.com/apppasswords
   - Copy the 16-character password (you won't see it again).

2. **Create a Gemini API key (free tier)**
   - Go to https://aistudio.google.com/apikey and sign in.
   - Click "Get API key" → "Create API key". Copy it.
   - Google's free-tier model lineup changes fairly often. This project
     defaults to `gemini-2.5-flash` (set via the `GEMINI_MODEL` env var if
     you need to change it) — if you start seeing "model not found" errors,
     check https://ai.google.dev/gemini-api/docs/models for the current
     free-tier model id.

3. **Push this folder to a GitHub repo** (can be private).

4. **Add repo secrets** -> Settings -> Secrets and variables -> Actions ->
   New repository secret:
   - `GMAIL_USER` -- your Gmail address
   - `GMAIL_APP_PASSWORD` -- the App Password from step 1
   - `TO_EMAIL` -- where you want the digest sent
   - `GEMINI_API_KEY` -- the key from step 2

5. The workflow needs **write permission** to commit `data/seen_titles.json`
   back to the repo. This is already set in the workflow file
   (`permissions: contents: write`), but if your org has repo-level
   restrictions on Actions permissions, double check Settings -> Actions ->
   General -> Workflow permissions is set to "Read and write permissions".

6. **Test it manually** -- Actions tab -> "Daily SSC Current Affairs Digest"
   -> "Run workflow". Check your inbox, then check that
   `data/seen_titles.json` got committed with today's items.

7. **Run it again manually right after** -- you should get an email with
   *zero* repeated news items (MCQs aren't deduped, since GKToday only
   publishes one quiz post a day anyway).

## Local testing

```bash
pip install -r requirements.txt
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxxxxxxxxxxxxxx"
export TO_EMAIL="you@gmail.com"
export GEMINI_API_KEY="xxxxxxxxxxxxxxxx"   # optional — omitted = AI step skipped, all items kept
cd scripts
python main.py
```

Check each source alone, without sending an email:
```bash
python scripts/gktoday_fetch.py   # news digest (GKToday, paginated)
python scripts/hindu_fetch.py     # The Hindu, last 24h
python scripts/pib_fetch.py       # PIB (Hindi titles — see caveat above)
python scripts/gktoday_quiz.py    # MCQs
python scripts/merge_sources.py   # cross-source dedup demo (fake data)
python scripts/gemini_filter.py   # relevance/one-liner demo (fake data)
```

## How it fits together

1. `gktoday_fetch.py`, `hindu_fetch.py`, `pib_fetch.py` each independently
   scrape their source. If one throws, `main.py` logs it and continues with
   the other two rather than failing the whole run.
2. `gktoday_quiz.py` separately finds and parses today's MCQ quiz post.
3. `merge_sources.py` tags every item with its source and collapses
   same-story duplicates across sources.
4. `dedup.py` drops anything matching an item sent in the last 5 days
   (`data/seen_titles.json`).
5. `gemini_filter.py` scores relevance, writes one-liners, and translates
   PIB's Hindi titles — low-relevance items are dropped here.
6. `render_mail.py` renders everything (news + quiz) into one HTML email.
7. `send_mail.py` sends it via Gmail SMTP with an App Password.
8. `main.py` wires the above together and, **only after the email sends
   successfully**, writes the updated seen-titles list back to
   `data/seen_titles.json`.
9. `.github/workflows/digest.yml` runs `main.py` daily (06:30 IST) via
   `workflow_dispatch`/`schedule`, then commits the updated
   `data/seen_titles.json` back to the repo.

## If it stops working

- **GKToday** prints "No items fetched" if the news digest selectors break
  -- inspect https://www.gktoday.in/current-affairs/ and adjust the
  heading/paragraph walk in `gktoday_fetch.py`.
- **The Hindu** — if a feed URL 404s or changes shape, `hindu_fetch.py`
  logs it per-feed and continues with the others; check the `FEED_SECTIONS`
  list against https://www.thehindu.com's current section RSS links.
- **PIB** returns an empty list if the ministry-heading walk breaks, or if
  PIB reworks the page enough that `#pageContent` / the
  `PressReleaseDetail.aspx?PRID=` link pattern no longer matches -- inspect
  https://www.pib.gov.in/allRel.aspx. See the caveat section above first.
- **Gemini** — if `enrich_items()` logs a call failure or bad JSON, it's
  failing open (every item kept, untranslated) by design; check
  `GEMINI_API_KEY` is set and `GEMINI_MODEL` is still a valid free-tier
  model id.
- **Quiz** — `gktoday_quiz.py` returns an empty list if the quiz page's
  `[A]...[D] ... Correct Answer:` text pattern changes, or if the listing
  page stops linking to `daily-current-affairs-quiz-*` posts -- inspect
  https://www.gktoday.in/gk-current-affairs-quiz-questions-answers/.
- If duplicates start showing up, check `data/seen_titles.json` is actually
  being committed by the workflow (see step 5 above about permissions).

## Weekly PDF report

Every time `main.py` sends a digest successfully, it also appends that
day's items (title, one-liner summary, category, source, importance) to
`data/weekly_items.json` — a rolling 7-day window, pruned the same way
`seen_titles.json` is (see `weekly_store.py`).

`weekly_report.py` reads that file, groups the week's items into the same
9 SSC sections as the daily email, and renders a concise PDF
(`data/weekly_report.pdf`, via `fpdf2`) which it emails as an attachment
using the same `GMAIL_USER` / `GMAIL_APP_PASSWORD` / `TO_EMAIL` secrets as
the daily digest — no new secrets needed.

`.github/workflows/weekly_report.yml` runs it every **Sunday at 07:00
IST** (after that morning's own daily digest has already landed in the
weekly store), and can also be triggered manually from the Actions tab.
If nothing was sent all week, it logs that and skips sending an email.

Test it locally:

```bash
python scripts/weekly_report.py   # reads data/weekly_items.json, sends the PDF
```

If it stops working: **Weekly report** comes up empty ("No items
collected this week") if `data/weekly_items.json` is empty or missing —
check that `digest.yml`'s commit step is actually committing it (same
permissions caveat as `seen_titles.json`, see Setup step 5).

## What's next

- **Phase 3**: weak-topic tracking, spaced revision, personalized MCQs
  (built on the relevance/category data Gemini is now attaching to every
  item).
