"""HTTP caching for the data endpoints.

Responses carry an ETag derived from their body and `Cache-Control: no-cache`,
so browsers keep a copy but check it with the server before every use. An
unchanged dataset costs a tiny 304 reply; a re-imported dataset is picked up on
the next request instead of hiding behind a fixed max-age.
"""
import hashlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CACHED_PATH_PREFIXES = ("/api/climate", "/api/districts")
CACHE_CONTROL = "no-cache"


def _etag_matches(if_none_match: str, etag: str) -> bool:
    # The comparison is weak (RFC 9110 13.1.2): ignore the W/ prefix.
    tags = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
    return "*" in tags or etag.removeprefix("W/") in tags


class DataETagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if (
            request.method != "GET"
            or response.status_code != 200
            or not request.url.path.startswith(CACHED_PATH_PREFIXES)
        ):
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        # Weak because GZipMiddleware may re-encode the body after this point.
        etag = f'W/"{hashlib.blake2b(body, digest_size=16).hexdigest()}"'

        if _etag_matches(request.headers.get("if-none-match", ""), etag):
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": CACHE_CONTROL})

        headers = dict(response.headers)
        headers["etag"] = etag
        headers["cache-control"] = CACHE_CONTROL
        return Response(content=body, status_code=200, headers=headers)
