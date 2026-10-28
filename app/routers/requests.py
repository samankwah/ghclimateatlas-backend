"""Climate data request endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.models.schemas import ClimateDataRequest, ClimateDataRequestResponse
from app.services.email import SMTPConfigurationError, send_data_request_confirmation

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_REQUESTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "requests"
    / "climate_data_requests.jsonl"
)


def _requests_path() -> Path:
    return Path(os.getenv("CLIMATE_REQUESTS_PATH", str(DEFAULT_REQUESTS_PATH)))


def _generate_request_id(submitted_at: datetime) -> str:
    date_part = submitted_at.strftime("%Y%m%d")
    random_part = secrets.token_hex(3).upper()
    return f"CDR-{date_part}-{random_part}"


def _append_request(record: dict) -> None:
    path = _requests_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


@router.post("", response_model=ClimateDataRequestResponse)
async def create_climate_data_request(payload: ClimateDataRequest):
    submitted_at = datetime.now(timezone.utc)
    request_id = _generate_request_id(submitted_at)
    record = {
        "request_id": request_id,
        "submitted_at": submitted_at.isoformat(),
        **payload.model_dump(),
    }

    try:
        _append_request(record)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to save climate data request",
        ) from exc

    warning = None
    email_status = "sent"
    try:
        # smtplib blocks for up to its timeout per step; keep that off the event loop.
        await asyncio.to_thread(send_data_request_confirmation, record)
    except SMTPConfigurationError:
        # A server without SMTP configured is a normal state, not a fault.
        logger.info("Confirmation email skipped for %s: SMTP is not configured", request_id)
        email_status = "not_configured"
        warning = (
            "Request saved. Confirmation email delivery is not configured "
            "for this server yet."
        )
    except Exception:  # noqa: BLE001 - delivery failure is non-fatal here.
        # Log the reason: without this a bad SMTP credential fails invisibly,
        # because the caller still gets a 200 with the request saved.
        logger.warning("Confirmation email failed for %s", request_id, exc_info=True)
        email_status = "failed"
        warning = (
            "Request saved. Confirmation email could not be sent right now. "
            "Keep your Request ID for follow-up."
        )

    return ClimateDataRequestResponse(
        request_id=request_id,
        submitted_at=record["submitted_at"],
        status="received",
        email_status=email_status,
        warning=warning,
    )
