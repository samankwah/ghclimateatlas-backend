"""Unit tests for the GMet Climate Atlas update scraper.

Run with: python -m unittest discover -s tests -t .

The fixtures are real (trimmed) responses from
https://www.meteo.gov.gh/news/?service=15 and /publications/?service=15,
including the "Featured" block that sits above the filtered results.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.services import gmet_news

FIXTURES = Path(__file__).parent / "fixtures"
SITE = "https://www.meteo.gov.gh"
ELLIPSIS = "…"
REPLACEMENT = "�"


def read_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseListingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.news = gmet_news.parse_listing(
            read_fixture("news_service15.html"), "news", SITE
        )
        cls.publications = gmet_news.parse_listing(
            read_fixture("publications_service15.html"), "publication", SITE
        )

    def test_reads_every_result_card(self):
        self.assertEqual(len(self.news), 6)
        self.assertEqual(len(self.publications), 3)

    def test_excludes_the_featured_block(self):
        # The featured item ignores the service filter, so it must not appear.
        urls = [item["url"] for item in self.news]
        self.assertNotIn(
            SITE
            + "/news/gmet-strengthens-aeronautical-meteorological-capacity"
            + "-with-second-refresher-training/",
            urls,
        )

    def test_titles_are_not_truncated(self):
        titles = [item["title"] for item in self.news]
        self.assertIn(
            "GMet Engages NDPC on Climate Atlas Application for National Development Planning",
            titles,
        )
        for title in titles:
            self.assertNotIn(ELLIPSIS, title)

    def test_normalises_dates_to_iso(self):
        by_title = {item["title"]: item for item in self.news}
        item = by_title[
            "GMet Engages NDPC on Climate Atlas Application for National Development Planning"
        ]
        self.assertEqual(item["published_at"], "2026-07-20")
        self.assertEqual(item["published_label"], "20 Jul 2026")

    def test_captures_category_kind_url_and_image(self):
        item = next(
            entry
            for entry in self.news
            if entry["id"] == "gmet-begins-python-training-to-strengthen-climate-data-analytics"
        )
        self.assertEqual(item["category"], "Articles")
        self.assertEqual(item["kind"], "news")
        self.assertTrue(item["url"].startswith(SITE + "/news/"))
        self.assertEqual(item["image_url"], SITE + "/media/images/GMET2087.original.jpg")
        self.assertIn("Danish Meteorological Institute", item["summary"])

    def test_strips_the_upstream_truncation_marker(self):
        for item in self.news + self.publications:
            self.assertFalse(item["summary"].endswith(ELLIPSIS), item["summary"])
            self.assertFalse(item["summary"].endswith(REPLACEMENT), item["summary"])

    def test_publication_kind_and_categories(self):
        self.assertEqual({item["kind"] for item in self.publications}, {"publication"})
        self.assertIn("Bulletins", {item["category"] for item in self.publications})

    def test_unknown_markup_yields_nothing(self):
        # A ClimWeb upgrade that renames the card class must not half-parse.
        renamed = read_fixture("news_service15.html").replace("pub-item", "story-item")
        self.assertEqual(gmet_news.parse_listing(renamed, "news", SITE), [])


class DateParsingTests(unittest.TestCase):
    def test_supported_formats(self):
        self.assertEqual(gmet_news.parse_published_date("27 Aug 2026"), "2026-08-27")
        self.assertEqual(gmet_news.parse_published_date("27 August 2026"), "2026-08-27")
        self.assertEqual(gmet_news.parse_published_date("June 10, 2025"), "2025-06-10")
        self.assertEqual(gmet_news.parse_published_date("  14 May 2026 "), "2026-05-14")

    def test_unparseable_input(self):
        self.assertIsNone(gmet_news.parse_published_date(""))
        self.assertIsNone(gmet_news.parse_published_date("last Tuesday"))


class TruncationTests(unittest.TestCase):
    def test_removes_trailing_markers(self):
        self.assertEqual(gmet_news.strip_truncation("A summary" + ELLIPSIS), "A summary")
        self.assertEqual(gmet_news.strip_truncation("A summary" + REPLACEMENT), "A summary")
        self.assertEqual(gmet_news.strip_truncation("A summary..."), "A summary")

    def test_keeps_a_legitimate_full_stop(self):
        self.assertEqual(gmet_news.strip_truncation("A complete sentence."), "A complete sentence.")


class RenditionTests(unittest.TestCase):
    def test_rewrites_original_to_a_rendition(self):
        self.assertEqual(
            gmet_news.rendition_url(SITE + "/media/images/IMG_3574.original.jpg"),
            SITE + "/media/images/IMG_3574.width-800.jpg",
        )

    def test_handles_the_lazy_placeholder_variant(self):
        self.assertEqual(
            gmet_news.rendition_url(SITE + "/media/images/forecast.original_lazy.jpg"),
            SITE + "/media/images/forecast.width-800.jpg",
        )

    def test_leaves_unrecognised_urls_alone(self):
        self.assertIsNone(gmet_news.rendition_url(None))
        self.assertIsNone(gmet_news.rendition_url(SITE + "/media/images/logo.png"))


class MergeItemsTests(unittest.TestCase):
    def make(self, url, published_at, title="Item"):
        return {"url": url, "published_at": published_at, "title": title}

    def test_orders_newest_first_and_caps(self):
        group = [
            self.make("/a", "2025-01-01"),
            self.make("/b", "2026-08-27"),
            self.make("/c", "2026-05-14"),
        ]
        merged = gmet_news.merge_items([group], max_items=2)
        self.assertEqual([item["url"] for item in merged], ["/b", "/c"])

    def test_keeps_upstream_order_within_a_date(self):
        group = [
            self.make("/first", "2026-08-27", "Zebra"),
            self.make("/second", "2026-08-27", "Alpha"),
        ]
        merged = gmet_news.merge_items([group])
        self.assertEqual([item["url"] for item in merged], ["/first", "/second"])

    def test_dedupes_by_url_across_groups(self):
        merged = gmet_news.merge_items(
            [[self.make("/a", "2026-01-01")], [self.make("/a", "2026-01-01")]]
        )
        self.assertEqual(len(merged), 1)

    def test_undated_items_sort_last(self):
        merged = gmet_news.merge_items(
            [[self.make("/undated", None), self.make("/dated", "2020-01-01")]]
        )
        self.assertEqual([item["url"] for item in merged], ["/dated", "/undated"])


class CacheAndFallbackTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache_file = Path(directory.name) / "gmet_news.json"
        self.set_env("GMET_NEWS_CACHE_PATH", str(self.cache_file))

    def set_env(self, name, value):
        previous = os.environ.get(name)

        def restore():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous

        os.environ[name] = value
        self.addCleanup(restore)

    def unreachable_upstream(self):
        self.set_env("GMET_NEWS_BASE_URL", "http://127.0.0.1:9")
        self.set_env("GMET_NEWS_TIMEOUT", "1")

    def write_cache(self, payload):
        self.cache_file.write_text(json.dumps(payload), encoding="utf-8")

    def test_read_cache_rejects_an_empty_feed(self):
        self.write_cache({"fetched_at": "2026-09-01T00:00:00+00:00", "items": []})
        self.assertIsNone(gmet_news.read_cache())

    def test_read_cache_rejects_unreadable_json(self):
        self.cache_file.write_text("{not json", encoding="utf-8")
        self.assertIsNone(gmet_news.read_cache())

    def test_fresh_cache_is_served_without_touching_the_network(self):
        self.unreachable_upstream()
        self.set_env("GMET_NEWS_TTL_SECONDS", "3600")
        from datetime import datetime, timezone

        self.write_cache(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "items": [{"url": "/a", "title": "Cached", "id": "a"}],
                "source_url": "",
                "all_news_url": "",
                "all_publications_url": "",
            }
        )
        payload, stale = gmet_news.load_latest_updates()
        self.assertFalse(stale)
        self.assertEqual(payload["items"][0]["title"], "Cached")

    def test_serves_the_cache_marked_stale_when_the_upstream_fails(self):
        self.unreachable_upstream()
        self.set_env("GMET_NEWS_TTL_SECONDS", "60")
        self.write_cache(
            {
                "fetched_at": "2020-01-01T00:00:00+00:00",  # long expired
                "items": [{"url": "/a", "title": "Cached", "id": "a"}],
                "source_url": "",
                "all_news_url": "",
                "all_publications_url": "",
            }
        )
        payload, stale = gmet_news.load_latest_updates()
        self.assertTrue(stale)
        self.assertEqual(payload["items"][0]["title"], "Cached")

    def test_raises_when_there_is_no_cache_and_no_upstream(self):
        self.unreachable_upstream()
        with self.assertRaises(gmet_news.NewsUnavailable):
            gmet_news.load_latest_updates()

    def test_disabled_integration_refuses_to_refresh(self):
        self.set_env("GMET_NEWS_ENABLED", "false")
        with self.assertRaises(gmet_news.NewsUnavailable):
            gmet_news.refresh()


class ListingUrlTests(unittest.TestCase):
    def test_applies_the_climate_atlas_service_filter(self):
        self.assertEqual(
            gmet_news.listing_url("/news/", bypass=False), SITE + "/news/?service=15"
        )

    def test_cache_bust_adds_a_parameter(self):
        url = gmet_news.listing_url("/news/", bypass=True)
        self.assertIn("service=15", url)
        self.assertIn("_=", url)

    def test_source_links_carry_the_filter(self):
        links = gmet_news.source_links()
        self.assertIn("service=15", links["all_news_url"])
        self.assertIn("service=15", links["all_publications_url"])
        self.assertIn("section-latest-updates", links["source_url"])


if __name__ == "__main__":
    unittest.main()
