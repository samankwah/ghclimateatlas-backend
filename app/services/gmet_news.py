"""Climate Atlas updates published by GMet on meteo.gov.gh.

The GMet site is a Wagtail/ClimWeb install with no JSON API, no feed and no CORS
headers, so the browser cannot read it directly. This service mirrors the
"Latest Updates" section GMet curates on its own Climate Atlas page, filling in
each card's full record from the two listing pages filtered to GMet's "Climate
Atlas" service tag (the curated cards truncate their snippets), and adds the
first pages of the unfiltered news listing, where most of the Atlas team's news
actually lands untagged. Every item must be on topic (see RELEVANT_TOPICS):
GMet's picks include general agency news. Relevant curated picks lead; the rest
follow newest first. The result is kept in a small disk-backed cache shared by
every worker.

Freshness budget:

* GMet's edge caches pages for four hours and ignores a no-cache request header,
  but a cache-busting query parameter forces a fresh render, so the fetcher
  appends one unless GMET_NEWS_BYPASS_UPSTREAM_CACHE is turned off.
* A background loop refreshes every GMET_NEWS_TTL_SECONDS so requests are always
  served from a warm cache.
* The cache lives on disk, so a cold start serves the last known feed instantly
  instead of blocking on an external host.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait as wait_for_futures
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.meteo.gov.gh"
DEFAULT_SERVICE_ID = "15"  # "Climate Atlas" in GMet's service taxonomy.
DEFAULT_TTL_SECONDS = 1200
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "cache" / "gmet_news.json"
)

MAX_ITEMS = 8
RENDITION_SPEC = "width-800"
RENDITION_PROBE_BUDGET_SECONDS = 4.0
FORCED_REFRESH_INTERVAL_SECONDS = 60.0
LOCK_STALE_SECONDS = 90.0
USER_AGENT = "GhanaClimateAtlas/1.0 (+https://atlas.meteo.gov.gh)"

# (kind, listing path) - kind is what the API reports for each item.
LISTINGS: tuple[tuple[str, str], ...] = (
    ("news", "/news/"),
    ("publication", "/publications/"),
)

# GMet's Climate Atlas page and the section on it where editors pick the updates.
CURATED_PATH = "/climate-atlas/climate-change/"
CURATED_SECTION_ID = "section-latest-updates"

# Much of the Atlas team's news (DMI and Danish Embassy visits, the Python and
# climate data trainings) is never tagged "Climate Atlas", so the first pages of
# the unfiltered news listing are scanned as well and topic-filtered below.
# Twelve pages (about six months) reach back far enough to fill the carousel,
# e.g. the Climate Atlas launch article.
DEFAULT_ALL_NEWS_PAGES = 12

# Only updates on these topics are shown, matched against title and snippet:
# the Climate Atlas and KAPy, the Danish partnership behind them (DMI, the
# Danish Embassy), the team's Python and climate data trainings, and climate change.
RELEVANT_TOPICS = re.compile(
    r"climate[\s-]*atlas|\b(?:gh)?kapy\b"
    r"|\bDMI\b|danish|denmark"
    r"|\bpython\b|climate\s+data|climate\s+projections?"
    r"|climate[\s-]*change",
    re.IGNORECASE,
)

# On-topic articles the Atlas team chose not to show, by URL slug.
EXCLUDED_SLUGS: frozenset[str] = frozenset(
    {
        "gmet-hosts-training-on-climate-data-hydrological-modelling-and-early-warning-systems",
        "gmet-receives-joint-delegation-from-denmark-and-gss-to-explore-data-collaboration",
        "gmet-dmi-and-danish-embassy-engage-mocdti-on-digital-transformation-priorities",
        "dmi-presents-findings-from-socio-economic-impact-assessment-and-it-gap-analysis-to-gmet-board-and-management",
        "gmet-and-partners-conclude-stakeholder-engagements-for-socio-economic-impact-assessment-of-weather-and-climate-services",
        "gmet-uk-met-office-and-dmi-commence-stakeholder-engagements-on-socio-economic-impact-assessment",
    }
)


class NewsUnavailable(RuntimeError):
    """Raised when no updates could be produced and nothing is cached."""


# ---------------------------------------------------------------------------
# Configuration (read per call so a restart with new env vars takes effect)
# ---------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def base_url() -> str:
    return _env("GMET_NEWS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def service_id() -> str:
    return _env("GMET_NEWS_SERVICE_ID", DEFAULT_SERVICE_ID)


def ttl_seconds() -> int:
    try:
        return max(60, int(_env("GMET_NEWS_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def timeout_seconds() -> float:
    try:
        return max(1.0, float(_env("GMET_NEWS_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def all_news_pages() -> int:
    try:
        return max(0, int(_env("GMET_NEWS_ALL_PAGES", str(DEFAULT_ALL_NEWS_PAGES))))
    except ValueError:
        return DEFAULT_ALL_NEWS_PAGES


def cache_path() -> Path:
    return Path(_env("GMET_NEWS_CACHE_PATH", str(DEFAULT_CACHE_PATH)))


def bypass_upstream_cache() -> bool:
    return _flag("GMET_NEWS_BYPASS_UPSTREAM_CACHE", True)


def is_enabled() -> bool:
    return _flag("GMET_NEWS_ENABLED", True)


def listing_url(path: str, bypass: bool | None = None) -> str:
    """Build a service-filtered listing URL, optionally cache-busted."""
    params: dict[str, str] = {"service": service_id()}
    should_bypass = bypass_upstream_cache() if bypass is None else bypass
    if should_bypass:
        params["_"] = str(int(time.time()))
    return f"{base_url()}{path}?{urlencode(params)}"


def all_news_url(page: int, bypass: bool | None = None) -> str:
    """Build an unfiltered news listing page URL, optionally cache-busted."""
    params: dict[str, str] = {"page": str(page)}
    should_bypass = bypass_upstream_cache() if bypass is None else bypass
    if should_bypass:
        params["_"] = str(int(time.time()))
    return f"{base_url()}/news/?{urlencode(params)}"


def curated_url(bypass: bool | None = None) -> str:
    """Build the Climate Atlas page URL, optionally cache-busted."""
    should_bypass = bypass_upstream_cache() if bypass is None else bypass
    query = f"?{urlencode({'_': str(int(time.time()))})}" if should_bypass else ""
    return f"{base_url()}{CURATED_PATH}{query}"


def source_links() -> dict[str, str]:
    """Public, human-facing links that accompany the feed."""
    query = urlencode({"service": service_id()})
    return {
        "source_url": f"{base_url()}{CURATED_PATH}#{CURATED_SECTION_ID}",
        "all_news_url": f"{base_url()}/news/?{query}",
        "all_publications_url": f"{base_url()}/publications/?{query}",
    }


# ---------------------------------------------------------------------------
# Parsing (pure - no I/O, this is what the unit tests drive)
# ---------------------------------------------------------------------------

_WHITESPACE = re.compile(r"\s+")
# Zero-width and direction marks GMet's editor leaves in some titles.
_INVISIBLE = re.compile("[​-‏⁠﻿]")
# Snippets are truncated upstream with an ellipsis, sometimes mangled to U+FFFD.
_TRAILING_TRUNCATION = re.compile("(?:\\s|…|�|\\.{3})+$")
# Wagtail renditions replace the ".original" marker: foo.original.jpg -> foo.width-800.jpg
_ORIGINAL_MARKER = re.compile(r"\.original(?:_lazy)?(?=\.[A-Za-z0-9]+$)")

_DATE_FORMATS = (
    "%d %b %Y",   # 27 Aug 2026 - the format every listing currently uses
    "%d %B %Y",   # 27 August 2026
    "%b %d, %Y",  # Aug 27, 2026
    "%B %d, %Y",  # August 27, 2026
    "%Y-%m-%d",
    "%d/%m/%Y",
)


def _text(node: Any) -> str:
    if node is None:
        return ""
    return _WHITESPACE.sub(" ", _INVISIBLE.sub("", node.get_text(" ", strip=True))).strip()


def strip_truncation(value: str) -> str:
    """Drop the trailing ellipsis GMet appends to truncated snippets."""
    return _TRAILING_TRUNCATION.sub("", value).strip()


def parse_published_date(label: str) -> str | None:
    """Normalise a listing date label to an ISO YYYY-MM-DD string."""
    candidate = _WHITESPACE.sub(" ", label or "").strip()
    if not candidate:
        return None
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(candidate, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def rendition_url(image_url: str | None, spec: str = RENDITION_SPEC) -> str | None:
    """Return the Wagtail rendition URL for an original media URL, if derivable."""
    if not image_url:
        return None
    replaced, count = _ORIGINAL_MARKER.subn(f".{spec}", image_url)
    return replaced if count else None


def slug_from_url(url: str) -> str:
    segments = [segment for segment in urlparse(url).path.split("/") if segment]
    return segments[-1] if segments else url


def parse_listing(html: str, kind: str, site_url: str | None = None) -> list[dict[str, Any]]:
    """Extract update cards from a GMet news or publications listing page.

    Only ``div.result-list-item.pub-item`` nodes are read, which deliberately
    excludes the "Featured" block above the results - that block ignores the
    service filter and would otherwise leak unrelated items into the feed.
    """
    site = (site_url or base_url()).rstrip("/") + "/"
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []

    for node in soup.select("div.result-list-item.pub-item"):
        link = node.select_one("a.pub-title")
        if link is None:
            continue
        href = (link.get("href") or "").strip()
        title = _text(link)
        if not href or not title:
            continue

        url = urljoin(site, href)
        image = node.select_one("a.pub-thumb img")
        image_src = ""
        if image is not None:
            image_src = (image.get("data-progressive") or image.get("src") or "").strip()
        published_label = _text(node.select_one("span.pub-date"))

        items.append(
            {
                "id": slug_from_url(url),
                "kind": kind,
                "title": title,
                "summary": strip_truncation(_text(node.select_one("p.pub-snippet"))),
                "category": _text(node.select_one("span.pub-tag")) or "Update",
                "published_at": parse_published_date(published_label),
                "published_label": published_label,
                "url": url,
                "image_url": urljoin(site, image_src) if image_src else None,
                "image_fallback_url": None,
            }
        )

    return items


def parse_curated(html: str, site_url: str | None = None) -> list[dict[str, Any]]:
    """Extract the hand-picked cards from the Climate Atlas page's Latest Updates.

    The visible titles and snippets there are cut short, so the full title is
    taken from the card image's alt text. Order is GMet's own and is kept.
    """
    site = (site_url or base_url()).rstrip("/") + "/"
    soup = BeautifulSoup(html, "html.parser")
    section = soup.find(id=CURATED_SECTION_ID)
    if section is None:
        return []

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in section.select(".update-card"):
        link = card.select_one(".card-content a[href]")
        if link is None:
            continue
        href = (link.get("href") or "").strip()
        if not href:
            continue
        url = urljoin(site, href)
        if url in seen:
            continue

        image = card.select_one(".card-image img")
        alt = _INVISIBLE.sub("", (image.get("alt") or "") if image is not None else "")
        title = _WHITESPACE.sub(" ", alt).strip()
        title = title or strip_truncation(_text(link))
        if not title:
            continue
        seen.add(url)

        image_src = ""
        if image is not None:
            image_src = (image.get("data-progressive") or image.get("src") or "").strip()
        published_label = _text(card.select_one(".card-footer > span.card-footer-item"))

        items.append(
            {
                "id": slug_from_url(url),
                "kind": "publication" if "/publications/" in urlparse(url).path else "news",
                "title": title,
                "summary": strip_truncation(_text(card.select_one(".card-content .content"))),
                "category": _text(card.select_one(".card-content .tag")) or "Update",
                "published_at": parse_published_date(published_label),
                "published_label": published_label,
                "url": url,
                "image_url": urljoin(site, image_src) if image_src else None,
                "image_fallback_url": None,
            }
        )

    return items


def select_curated(
    curated: Sequence[dict[str, Any]],
    listed: Iterable[dict[str, Any]],
    max_items: int = MAX_ITEMS,
) -> list[dict[str, Any]]:
    """Keep GMet's curated picks and order, preferring each one's full listing record."""
    by_url = {item["url"]: item for item in listed if item.get("url")}
    return [by_url.get(item["url"], item) for item in curated][:max_items]


def is_relevant(item: dict[str, Any]) -> bool:
    """True when an update matches ``RELEVANT_TOPICS`` and is not excluded."""
    if slug_from_url(item.get("url") or "") in EXCLUDED_SLUGS:
        return False
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    return RELEVANT_TOPICS.search(text) is not None


def select_relevant(
    curated: Sequence[dict[str, Any]],
    listed: Iterable[dict[str, Any]],
    max_items: int = MAX_ITEMS,
) -> list[dict[str, Any]]:
    """GMet's relevant curated picks first, then relevant listing items newest first."""
    listed = list(listed)
    picks = [item for item in select_curated(curated, listed, max_items=len(curated)) if is_relevant(item)]
    picked = {item["url"] for item in picks}
    rest = merge_items([[item for item in listed if is_relevant(item) and item.get("url") not in picked]])
    return (picks + rest)[:max_items]


def merge_items(
    groups: Iterable[Sequence[dict[str, Any]]],
    max_items: int = MAX_ITEMS,
) -> list[dict[str, Any]]:
    """Dedupe by URL and order newest first, capped at ``max_items``.

    The sort key is the date alone: Python's sort is stable, so items sharing a
    date keep GMet's own ordering rather than being shuffled alphabetically.
    """
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in chain.from_iterable(groups):
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        merged.append(item)

    merged.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    return merged[:max_items]


# ---------------------------------------------------------------------------
# Image renditions
# ---------------------------------------------------------------------------

# Media URLs are stable, so a probe result is worth keeping for the process life.
_rendition_probes: dict[str, bool] = {}


def _probe_rendition(client: httpx.Client, url: str) -> bool:
    cached = _rendition_probes.get(url)
    if cached is not None:
        return cached
    try:
        response = client.head(url)
        exists = response.status_code == 200
    except httpx.HTTPError:
        exists = False
    _rendition_probes[url] = exists
    return exists


def resolve_images(client: httpx.Client, items: Sequence[dict[str, Any]]) -> None:
    """Point each item at the ~85 KB rendition instead of the 2-3 MB original.

    Probes run concurrently under a short budget; anything unresolved simply
    keeps the original URL, so a slow or unreachable media host costs at most
    ``RENDITION_PROBE_BUDGET_SECONDS`` and never fails the refresh.
    """
    candidates: list[tuple[dict[str, Any], str]] = []
    for item in items:
        original = item.get("image_url")
        candidate = rendition_url(original)
        if candidate and candidate != original:
            candidates.append((item, candidate))

    if not candidates:
        return

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_probe_rendition, client, candidate): (item, candidate)
            for item, candidate in candidates
        }
        done, _ = wait_for_futures(futures, timeout=RENDITION_PROBE_BUDGET_SECONDS)
        for future in done:
            item, candidate = futures[future]
            try:
                exists = future.result()
            except Exception:  # noqa: BLE001 - a probe failure just keeps the original.
                continue
            if exists:
                item["image_fallback_url"] = item["image_url"]
                item["image_url"] = candidate


# ---------------------------------------------------------------------------
# Disk-backed cache shared across gunicorn workers
# ---------------------------------------------------------------------------

def _lock_path() -> Path:
    path = cache_path()
    return path.with_name(path.name + ".lock")


def _acquire_lock() -> bool:
    """Best-effort cross-process lock so only one worker scrapes per cycle."""
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            return False
        if age < LOCK_STALE_SECONDS:
            return False
        # The holder died mid-refresh; reclaim the lock.
        try:
            path.unlink()
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return False
    except OSError:
        return False

    try:
        os.write(handle, str(os.getpid()).encode("ascii"))
    finally:
        os.close(handle)
    return True


def _release_lock() -> None:
    try:
        _lock_path().unlink()
    except OSError:
        pass


def read_cache() -> dict[str, Any] | None:
    try:
        with cache_path().open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return None
    # Feeds cached before the topic filter existed may hold off-topic items.
    payload["items"] = [item for item in payload["items"] if isinstance(item, dict) and is_relevant(item)]
    return payload


def _write_cache(payload: dict[str, Any]) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(temporary, path)
    except OSError:
        logger.warning("Could not write the GMet news cache to %s", path)
        try:
            temporary.unlink()
        except OSError:
            pass


def feed_signature() -> str:
    """Identifies what produced a feed, so a cache from older rules is refetched."""
    excluded = ",".join(sorted(EXCLUDED_SLUGS))
    return f"{RELEVANT_TOPICS.pattern}|excluded={excluded}|pages={all_news_pages()}|service={service_id()}"


def _is_expired(payload: dict[str, Any]) -> bool:
    # A topic or source change must show up at once, not after the TTL runs out.
    if payload.get("signature") != feed_signature():
        return True
    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, str):
        return True
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except ValueError:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - fetched).total_seconds()
    return age >= ttl_seconds()


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _fetch_listings() -> list[dict[str, Any]]:
    """Scrape the curated section and both listings; return image-resolved items."""
    groups: list[list[dict[str, Any]]] = []
    site = base_url()
    with httpx.Client(
        timeout=timeout_seconds(),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        curated: list[dict[str, Any]] = []
        try:
            response = client.get(curated_url())
            response.raise_for_status()
            curated = parse_curated(response.text, site)
        except httpx.HTTPError as exc:
            logger.warning("Could not read GMet's curated Climate Atlas updates: %s", exc)
        if not curated:
            logger.warning("No curated Climate Atlas updates found; using the listings alone")

        # The tagged listings plus the first pages of all news, fetched together.
        # A page that fails is skipped; the rest still make a feed.
        pages = [(kind, listing_url(path)) for kind, path in LISTINGS]
        pages += [("news", all_news_url(page)) for page in range(1, all_news_pages() + 1)]

        def fetch(page: tuple[str, str]) -> list[dict[str, Any]]:
            kind, url = page
            response = client.get(url)
            response.raise_for_status()
            return parse_listing(response.text, kind, site)

        errors: list[Exception] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            for (kind, url), future in zip(pages, [pool.submit(fetch, page) for page in pages]):
                try:
                    groups.append(future.result())
                except httpx.HTTPError as exc:
                    logger.warning("Could not read GMet %s listing %s: %s", kind, url, exc)
                    errors.append(exc)

        if not curated and errors and len(errors) == len(pages):
            raise errors[0]

        # An empty parse means the upstream template changed, not that GMet has
        # no updates. Treat it as a failure so the previous feed is kept.
        if not curated and not any(groups):
            raise NewsUnavailable(
                "No update cards found on the GMet listings - the upstream markup may have changed"
            )

        # Cards parsed but none on topic is a valid, empty feed.
        items = select_relevant(curated, chain.from_iterable(groups))
        resolve_images(client, items)

    return items


def refresh() -> dict[str, Any]:
    """Scrape GMet and write the shared cache. Raises ``NewsUnavailable``."""
    if not is_enabled():
        raise NewsUnavailable("GMet news integration is disabled")

    if not _acquire_lock():
        # Another worker is already refreshing; use whatever is on disk.
        cached = read_cache()
        if cached is not None:
            return cached
        raise NewsUnavailable("A refresh is already in progress")

    try:
        items = _fetch_listings()
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "signature": feed_signature(),
            "items": items,
            **source_links(),
        }
        # Written while still holding the lock, so "one worker refreshes per
        # cycle" covers the write and not just the fetch.
        _write_cache(payload)
    except NewsUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - any upstream failure is non-fatal here.
        raise NewsUnavailable(f"Could not read updates from GMet: {exc}") from exc
    finally:
        _release_lock()

    logger.info("Refreshed GMet Climate Atlas updates (%d items)", len(items))
    return payload


def refresh_if_due() -> None:
    """Refresh only when the shared cache has aged out (used by the loop)."""
    cached = read_cache()
    if cached is not None and not _is_expired(cached):
        return
    refresh()


_last_forced_refresh = 0.0


def load_latest_updates(fresh: bool = False) -> tuple[dict[str, Any], bool]:
    """Return ``(payload, stale)`` for the API.

    ``stale`` is true when the cache is being served because the upstream fetch
    failed, so the UI can say so rather than presenting old news as current.
    """
    global _last_forced_refresh

    cached = read_cache()

    if fresh:
        now = time.monotonic()
        if now - _last_forced_refresh < FORCED_REFRESH_INTERVAL_SECONDS and cached is not None:
            # Throttled: a forced refresh already ran very recently.
            return cached, _is_expired(cached)
        _last_forced_refresh = now
    elif cached is not None and not _is_expired(cached):
        return cached, False

    try:
        return refresh(), False
    except Exception as exc:  # noqa: BLE001 - fall back to the cache when possible.
        if cached is not None:
            logger.warning("Serving cached GMet updates: %s", exc)
            return cached, True
        raise NewsUnavailable(str(exc)) from exc


# ---------------------------------------------------------------------------
# Background refresh loop
# ---------------------------------------------------------------------------

_refresh_task: asyncio.Task[None] | None = None


async def _refresh_loop() -> None:
    # Jitter the start so two gunicorn workers do not contend on every cycle.
    await asyncio.sleep(random.uniform(1.0, 8.0))
    while True:
        try:
            await asyncio.to_thread(refresh_if_due)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive across failures.
            logger.warning("Scheduled GMet news refresh failed: %s", exc)
        # Poll at half the TTL so the effective staleness bound stays at the TTL
        # even when the other worker wrote the cache mid-cycle.
        await asyncio.sleep(max(60, ttl_seconds() // 2) + random.uniform(0, 15))


def start_refresh_loop() -> None:
    global _refresh_task
    if not is_enabled():
        logger.info("GMet news integration disabled; not starting the refresh loop")
        return
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = asyncio.create_task(_refresh_loop())


async def stop_refresh_loop() -> None:
    global _refresh_task
    task = _refresh_task
    _refresh_task = None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown must not raise.
        pass
