"""Unit tests for CORS origin resolution.

Run with: python -m unittest discover -s tests -t .

Regression cover for the outage where the deployed CORS_ORIGINS listed only
atlas.meteo.gov.gh, so the Netlify frontend got no Access-Control-Allow-Origin
header and every map request failed in the browser.
"""

import os
import unittest
from unittest import mock

from app.main import (
    _parse_cors_origins,
    default_cors_origins,
    first_party_origins,
)

NETLIFY = "https://ghclimateatlas.netlify.app"
ATLAS = "https://atlas.meteo.gov.gh"


def with_env(value):
    """Patch CORS_ORIGINS, or remove it entirely when value is None."""
    if value is None:
        return mock.patch.dict(os.environ, {}, clear=False)
    return mock.patch.dict(os.environ, {"CORS_ORIGINS": value})


class ParseCorsOriginsTests(unittest.TestCase):
    def test_unset_env_returns_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CORS_ORIGINS", None)
            self.assertEqual(_parse_cors_origins(), default_cors_origins)

    def test_defaults_cover_both_first_party_sites(self):
        for origin in (ATLAS, NETLIFY):
            self.assertIn(origin, default_cors_origins)

    def test_narrow_config_still_allows_first_party_origins(self):
        # The exact production value that caused the outage.
        with with_env("http://localhost:5173,http://localhost:3000," + ATLAS):
            origins = _parse_cors_origins()
        self.assertIn(NETLIFY, origins)
        self.assertIn(ATLAS, origins)
        self.assertIn("http://localhost:5173", origins)

    def test_configured_extras_are_kept(self):
        with with_env("https://staging.example.org"):
            origins = _parse_cors_origins()
        self.assertIn("https://staging.example.org", origins)
        for origin in first_party_origins:
            self.assertIn(origin, origins)

    def test_blank_env_falls_back_to_defaults(self):
        with with_env("   "):
            self.assertEqual(_parse_cors_origins(), default_cors_origins)

    def test_invalid_entries_only_falls_back_to_defaults(self):
        with with_env("not-a-url,ftp://example.org"):
            self.assertEqual(_parse_cors_origins(), default_cors_origins)

    def test_trailing_slashes_are_normalised(self):
        with with_env("https://staging.example.org/"):
            self.assertIn("https://staging.example.org", _parse_cors_origins())

    def test_no_duplicates(self):
        with with_env(f"{NETLIFY},{ATLAS}"):
            origins = _parse_cors_origins()
        self.assertEqual(len(origins), len(set(origins)))


if __name__ == "__main__":
    unittest.main()
