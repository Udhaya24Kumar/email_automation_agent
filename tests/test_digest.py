import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import gemini_filter
import main
import weekly_store
from dedup import load_seen
from weekly_report import build_pdf


class DigestTests(unittest.TestCase):
    def test_preview_and_rerun_after_partial_outage(self):
        sent = {"title": "New national space mission", "url": "https://example.org/space"}
        excluded = {"title": "Routine cricket score", "url": "https://example.org/score"}
        quiz = [{"question": "Which mission?", "options": ["One", "Two"], "answer": "One"}]

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with (
                patch.object(main, "SEEN_PATH", path / "seen.json"),
                patch.object(main, "WEEKLY_PATH", path / "week.json"),
                patch.object(main, "fetch_today_digest", return_value=[sent, excluded]),
                patch.object(main, "fetch_hindu", side_effect=RuntimeError("offline")),
                patch.object(main, "fetch_pib", return_value=[]),
                patch.object(main, "fetch_today_quiz", return_value=quiz),
                patch.object(main, "enrich_items", side_effect=lambda items: [
                    dict(item, summary="A new national space mission.", importance=4) for item in items if item["title"] == sent["title"]
                ]),
                patch.object(main, "send_email") as send,
            ):
                with patch.object(sys, "argv", ["main", "--preview", str(path / "digest.html")]):
                    main.main()
                send.assert_not_called()
                self.assertIn(sent["title"], (path / "digest.html").read_text(encoding="utf-8"))
                self.assertFalse(main.SEEN_PATH.exists())

                with patch.object(sys, "argv", ["main"]):
                    main.main()
                    main.main()
                send.assert_called_once()
                self.assertEqual(weekly_store.load_week(main.WEEKLY_PATH)[0]["title"], sent["title"])
                self.assertNotIn(excluded["title"], [entry["title"] for entry in load_seen(main.SEEN_PATH)])

    def test_english_notes_include_source_evidence(self):
        article = {"title": "Bill proposed", "excerpt": "The bill has not passed.",
                   "url": "https://example.org/bill", "source": "hindu"}
        result = {
            "index": 0,
            "importance": 5,
            "headline_en": "Bill proposed for parliamentary debate",
            "summary_en": "The bill has not passed.",
            "keywords": ["Bill: proposed", "Status: not passed"],
            "evidence": ["The bill has not passed.", "Bill proposed", "not passed"],
        }
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "fixture"}),
            patch.object(gemini_filter.genai, "Client"),
            patch.object(gemini_filter, "_call_gemini", return_value=[result]),
        ):
            item, = gemini_filter.enrich_items([article])
        self.assertEqual(item["title"], result["headline_en"])
        self.assertEqual(item["summary"], result["summary_en"])
        self.assertEqual(item["keywords"], result["keywords"])

    def test_malformed_batch_skips_news(self):
        pib = {"title": "Government release", "url": "https://example.org/pib", "source": "pib"}
        hindu = {"title": "Secondary article", "url": "https://example.org/news", "source": "hindu"}
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "fixture"}),
            patch.object(gemini_filter.genai, "Client"),
            patch.object(gemini_filter, "_call_gemini", return_value=[{"index": 0, "importance": "5"}]),
        ):
            self.assertEqual(gemini_filter.enrich_items([pib, hindu]), [])

    def test_hindi_fallback_is_not_sent_untranslated(self):
        hindi = {
            "title": "प्रधानमंत्री ने नई योजना की घोषणा की",
            "url": "https://example.org/pib-hindi",
            "source": "pib",
            "lang": "hi",
        }
        english = {
            "title": "Government announces defence programme",
            "url": "https://example.org/pib-en",
            "source": "pib",
            "lang": "en",
        }
        with patch.dict(os.environ, {}, clear=True):
            items = gemini_filter.enrich_items([hindi, english])
        self.assertEqual(items, [])


    def test_translation_keeps_evidence_and_original_title(self):
        article = {
            "title": "\u092d\u093e\u0930\u0924",
            "excerpt": "\u092d\u093e\u0930\u0924 2026",
            "source": "pib", "url": "https://example.org/release",
        }
        result = {
            "headline_en": "India announces programme in 2026",
            "summary_en": "India announces a programme in 2026.",
            "keywords": ["Country: India", "Year: 2026"],
            "evidence": [article["excerpt"], article["title"], "2026"],
        }
        item = gemini_filter._source_item(article, 4, result)
        self.assertEqual(item["original_title"], article["title"])
        self.assertEqual(item["lang"], "en")
        self.assertEqual(gemini_filter.filter_low_relevance([item]), [item])
        result["keywords"][0] = "Country: " + article["title"]
        with self.assertRaises(ValueError):
            gemini_filter._source_item(article, 4, result)

    def test_unsupported_figures_and_missing_evidence_are_rejected(self):
        article = {"title": "India publishes report", "excerpt": "Report published in 2026."}
        result = {
            "headline_en": "India publishes report",
            "summary_en": "India publishes report in 2027.",
            "keywords": ["Country: India", "Year: 2027"],
            "evidence": ["Report published in 2026.", "India", "2026"],
        }
        with self.assertRaises(ValueError):
            gemini_filter._source_item(article, 4, result)
        result["summary_en"] = "India publishes report."
        result["keywords"] = ["Country: India", "Year: 2026"]
        result["evidence"] = ["Invented source text", "India", "2026"]
        with self.assertRaises(ValueError):
            gemini_filter._source_item(article, 4, result)


class WeeklyTests(unittest.TestCase):
    def test_ist_week_includes_first_day(self):
        days = [{"date_added": f"2026-11-{day:02}"} for day in range(7, 17)]
        with patch.object(weekly_store, "today_ist", return_value=date(2026, 11, 15)):
            kept = weekly_store._prune(days)
        self.assertEqual(len(kept), 7)
        self.assertEqual(kept[0]["date_added"], "2026-11-09")

    def test_pdf_renders_long_unicode_items_across_pages(self):
        item = {
            "title": "Long title " * 15 + "\u092d\u093e\u0930\u0924",
            "summary": "Investment of \u20b910 crore. " * 30,
            "date_added": "2026-11-15",
            "source": "pib",
            "category": "national",
            "url": "https://example.org/release",
        }
        with tempfile.TemporaryDirectory() as folder:
            output = build_pdf([item] * 15, "2026-11-09", "2026-11-15", Path(folder) / "week.pdf")
            self.assertTrue(output.read_bytes().startswith(b"%PDF"))
            self.assertGreater(output.read_bytes().count(b"/Type /Page"), 2)


if __name__ == "__main__":
    unittest.main()
