"""Unit tests for the GMet Climate Atlas update scraper.

Run with: python -m unittest discover -s tests -t .

The fixtures are real (trimmed) responses from
https://www.meteo.gov.gh/news/?service=15 and /publications/?service=15,
including the "Featured" block that sits above the filtered results, and the
"Latest Updates" section of /climate-atlas/climate-change/.
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


class ParseCuratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.curated = gmet_news.parse_curated(
            read_fixture("climate_atlas_latest_updates.html"), SITE
        )

    def test_reads_gmets_picks_in_order(self):
        self.assertEqual(
            [item["id"] for item in self.curated],
            [
                "gmet-begins-stakeholder-engagement-on-establishment-of-wmo-regional-training-centre",
                "gmet-strengthens-aeronautical-meteorological-capacity-through-refresher-training",
                "2026-seasonal-forecast-for-northern-ghana",
                "meteorological-awareness-month-2025-newsletter",
            ],
        )

    def test_takes_the_full_title_from_the_image_alt(self):
        self.assertEqual(
            self.curated[0]["title"],
            "GMet Begins Stakeholder Engagement on Establishment of WMO Regional Training Centre",
        )
        for item in self.curated:
            self.assertNotIn(REPLACEMENT, item["title"])

    def test_reads_kind_category_date_and_image(self):
        forecast = self.curated[2]
        self.assertEqual(forecast["kind"], "publication")
        self.assertEqual(forecast["category"], "Bulletins")
        self.assertEqual(forecast["published_at"], "2026-05-14")
        self.assertEqual(
            forecast["image_url"],
            SITE + "/media/images/f2026_forecast_for_northern_ghana-2026-05-14-16.original.jpg",
        )
        self.assertEqual(self.curated[0]["kind"], "news")

    def test_missing_section_yields_nothing(self):
        self.assertEqual(gmet_news.parse_curated("<html><body></body></html>", SITE), [])

    def test_prefers_the_full_listing_record(self):
        listed = gmet_news.parse_listing(read_fixture("news_service15.html"), "news", SITE)
        selected = gmet_news.select_curated(self.curated, listed)
        self.assertEqual([item["url"] for item in selected], [item["url"] for item in self.curated])
        self.assertIs(selected[0], next(item for item in listed if item["url"] == selected[0]["url"]))
        # Items missing from the listings keep their curated card.
        self.assertIs(selected[3], self.curated[3])


class RelevanceTests(unittest.TestCase):
    def item(self, title, summary=""):
        return {"title": title, "summary": summary}

    def test_matches_the_atlas_team_topics(self):
        # Real GMet headlines the Atlas team's news has run under.
        for title in (
            "GMet Engages NDPC on Climate Atlas Application",
            "New GhKAPy projections released",
            "Training on the KAPy workflow",
            "Joint workshop with the Danish Meteorological Institute",
            "DMI Presents IT Gap Analysis Findings and Recommendations to GMet Board and Management",
            "GMet Receives Joint Delegation from Denmark and GSS to Explore Data Collaboration",
            "GMet, DMI and Danish Embassy Engage MoCDTI on Digital Transformation Priorities",
            "Move Beyond Training and Apply the Knowledge",
            "GMet hosts training on climate data, hydrological modelling and early warning systems",
            "Workshop on climate change adaptation",
            "Downscaled climate projections for Ghana",
        ):
            summary = "participants of the Python Training Programme" if title.startswith("Move") else ""
            self.assertTrue(gmet_news.is_relevant(self.item(title, summary)), title)

    def test_excluded_articles_are_dropped_despite_matching(self):
        slug = "gmet-receives-joint-delegation-from-denmark-and-gss-to-explore-data-collaboration"
        item = {
            "title": "GMet Receives Joint Delegation from Denmark and GSS to Explore Data Collaboration",
            "summary": "",
            "url": f"{SITE}/news/{slug}/",
        }
        self.assertIn(slug, gmet_news.EXCLUDED_SLUGS)
        self.assertFalse(gmet_news.is_relevant(item))

    def test_matches_on_the_snippet(self):
        self.assertTrue(gmet_news.is_relevant(self.item("Workshop", "Using the Ghana Climate Atlas")))

    def test_rejects_general_agency_news(self):
        curated = gmet_news.parse_curated(read_fixture("climate_atlas_latest_updates.html"), SITE)
        self.assertEqual([item for item in curated if gmet_news.is_relevant(item)], [])
        for title in (
            "Kapyong exchange visit",
            "WMO Conference Officer Engages GMet on Preparations for 19th WMO RA I Conference",
            "REQUEST FOR EXPRESSION OF INTEREST (EOI)",
            "Ghana Meteorological Agency Newsletter- July",
        ):
            self.assertFalse(gmet_news.is_relevant(self.item(title)), title)

    def test_selects_only_on_topic_items(self):
        curated = gmet_news.parse_curated(read_fixture("climate_atlas_latest_updates.html"), SITE)
        listed = gmet_news.parse_listing(read_fixture("news_service15.html"), "news", SITE) + gmet_news.parse_listing(
            read_fixture("publications_service15.html"), "publication", SITE
        )
        selected = gmet_news.select_relevant(curated, listed)
        self.assertEqual(
            [item["id"] for item in selected],
            [
                "beyond-training-and-apply-the-knowledge-dr-ignatius-kweku-williams-charges-trainees",
                "gmet-begins-python-training-to-strengthen-climate-data-analytics",
                "gmet-engages-ndpc-on-climate-atlas-application-for-national-development-planning",
            ],
        )

    def test_relevant_curated_picks_lead_then_listings_newest_first(self):
        def make(url, title, published_at):
            return {"url": url, "title": title, "summary": "", "published_at": published_at}

        curated = [make("/old-pick", "Climate Atlas pick", "2025-01-01"), make("/off", "Aviation", "2026-09-01")]
        listed = [
            make("/older", "DMI partnership talk", "2026-01-01"),
            make("/newer", "KAPy release", "2026-06-01"),
            make("/old-pick", "Climate Atlas pick (full)", "2025-01-01"),
        ]
        selected = gmet_news.select_relevant(curated, listed)
        self.assertEqual([item["url"] for item in selected], ["/old-pick", "/newer", "/older"])
        self.assertEqual(selected[0]["title"], "Climate Atlas pick (full)")


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

    def test_read_cache_accepts_an_empty_feed(self):
        # No on-topic updates is a valid feed, not a broken one.
        self.write_cache({"fetched_at": "2026-09-01T00:00:00+00:00", "items": []})
        self.assertEqual(gmet_news.read_cache()["items"], [])

    def test_read_cache_rejects_a_feed_without_items(self):
        self.write_cache({"fetched_at": "2026-09-01T00:00:00+00:00"})
        self.assertIsNone(gmet_news.read_cache())

    def test_read_cache_drops_off_topic_items(self):
        self.write_cache(
            {
                "fetched_at": "2026-09-01T00:00:00+00:00",
                "items": [
                    {"url": "/a", "title": "Aeronautical Refresher Training", "summary": ""},
                    {"url": "/b", "title": "Climate Atlas launch", "summary": ""},
                ],
            }
        )
        self.assertEqual([item["url"] for item in gmet_news.read_cache()["items"]], ["/b"])

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
                "signature": gmet_news.feed_signature(),
                "items": [{"url": "/a", "title": "Cached Climate Atlas update", "id": "a"}],
                "source_url": "",
                "all_news_url": "",
                "all_publications_url": "",
            }
        )
        payload, stale = gmet_news.load_latest_updates()
        self.assertFalse(stale)
        self.assertEqual(payload["items"][0]["title"], "Cached Climate Atlas update")

    def test_a_cache_from_older_topic_rules_is_refetched_at_once(self):
        from datetime import datetime, timezone

        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": [{"url": "/a", "title": "Cached Climate Atlas update", "id": "a"}],
        }
        self.assertTrue(gmet_news._is_expired(payload))
        payload["signature"] = gmet_news.feed_signature()
        self.assertFalse(gmet_news._is_expired(payload))

    def test_serves_the_cache_marked_stale_when_the_upstream_fails(self):
        self.unreachable_upstream()
        self.set_env("GMET_NEWS_TTL_SECONDS", "60")
        self.write_cache(
            {
                "fetched_at": "2020-01-01T00:00:00+00:00",  # long expired
                "items": [{"url": "/a", "title": "Cached Climate Atlas update", "id": "a"}],
                "source_url": "",
                "all_news_url": "",
                "all_publications_url": "",
            }
        )
        payload, stale = gmet_news.load_latest_updates()
        self.assertTrue(stale)
        self.assertEqual(payload["items"][0]["title"], "Cached Climate Atlas update")

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

    def test_all_news_url_pages_the_unfiltered_listing(self):
        self.assertEqual(gmet_news.all_news_url(3, bypass=False), SITE + "/news/?page=3")
        self.assertNotIn("service=", gmet_news.all_news_url(1, bypass=True))
        self.assertIn("_=", gmet_news.all_news_url(1, bypass=True))

    def test_curated_url_points_at_the_climate_atlas_page(self):
        self.assertEqual(gmet_news.curated_url(bypass=False), SITE + "/climate-atlas/climate-change/")
        self.assertIn("_=", gmet_news.curated_url(bypass=True))

    def test_source_links_carry_the_filter(self):
        links = gmet_news.source_links()
        self.assertIn("service=15", links["all_news_url"])
        self.assertIn("service=15", links["all_publications_url"])
        self.assertIn("section-latest-updates", links["source_url"])


if __name__ == "__main__":
    unittest.main()
