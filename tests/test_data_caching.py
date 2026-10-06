"""Tests for the ETag caching on the data endpoints.

Run with: python -m unittest discover -s tests -t .

Regression cover for re-imported sea-level data staying invisible: responses
were sent with `max-age=3600`, so browsers kept showing the old data for an
hour without asking the server.
"""

import unittest

from fastapi.testclient import TestClient

from app.main import app

SEA_LEVEL_URL = "/api/climate/sea_level_rise?period=2080&scenario=ssp585&percentile=p50"


class DataCachingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_data_responses_must_be_revalidated(self):
        response = self.client.get(SEA_LEVEL_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertTrue(response.headers["etag"].startswith('W/"'))

    def test_unchanged_data_returns_304(self):
        etag = self.client.get(SEA_LEVEL_URL).headers["etag"]
        response = self.client.get(SEA_LEVEL_URL, headers={"If-None-Match": etag})
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["etag"], etag)

    def test_changed_data_returns_full_response(self):
        response = self.client.get(SEA_LEVEL_URL, headers={"If-None-Match": 'W/"stale"'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"])

    def test_different_data_gets_a_different_etag(self):
        ssp585 = self.client.get(SEA_LEVEL_URL).headers["etag"]
        ssp126 = self.client.get(SEA_LEVEL_URL.replace("ssp585", "ssp126")).headers["etag"]
        self.assertNotEqual(ssp585, ssp126)

    def test_district_map_is_cached_the_same_way(self):
        response = self.client.get("/api/districts/map")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-cache")
        self.assertIn("etag", response.headers)

    def test_errors_are_not_cached(self):
        response = self.client.get("/api/climate/not_a_variable?period=2080&scenario=ssp585")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("etag", response.headers)


if __name__ == "__main__":
    unittest.main()
