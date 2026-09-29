"""Climate Atlas update feed sourced from meteo.gov.gh."""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.models.schemas import LatestUpdatesResponse
from app.services.gmet_news import MAX_ITEMS, NewsUnavailable, load_latest_updates

router = APIRouter()

# Short browser/CDN cache with a generous revalidation window: the backend keeps
# its own copy warm, so a client revalidation is a cheap 304 rather than a scrape.
CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=600"


def _etag(payload: dict, limit: int, stale: bool) -> str:
    fingerprint = json.dumps(
        {
            "limit": limit,
            "stale": stale,
            "fetched_at": payload.get("fetched_at"),
            "urls": [item.get("url") for item in payload.get("items", [])[:limit]],
        },
        sort_keys=True,
    )
    return '"' + hashlib.sha1(fingerprint.encode("utf-8")).hexdigest() + '"'


@router.get("/latest", response_model=LatestUpdatesResponse)
async def latest_updates(
    request: Request,
    response: Response,
    limit: int = Query(default=MAX_ITEMS, ge=1, le=MAX_ITEMS),
    fresh: bool = Query(default=False, description="Bypass the server cache (throttled)"),
):
    try:
        payload, stale = load_latest_updates(fresh=fresh)
    except NewsUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Climate Atlas updates are unavailable right now",
        ) from exc

    etag = _etag(payload, limit, stale)
    response.headers["Cache-Control"] = CACHE_CONTROL
    response.headers["ETag"] = etag

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=dict(response.headers))

    return LatestUpdatesResponse(
        items=payload.get("items", [])[:limit],
        fetched_at=payload.get("fetched_at", ""),
        stale=stale,
        source_url=payload.get("source_url", ""),
        all_news_url=payload.get("all_news_url", ""),
        all_publications_url=payload.get("all_publications_url", ""),
    )
