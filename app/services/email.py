"""SMTP email helpers for climate data request confirmations."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Mapping


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    from_email: str
    from_name: str
    use_tls: bool


class SMTPConfigurationError(RuntimeError):
    """Raised when confirmation email delivery has not been configured."""


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_smtp_config() -> SMTPConfig:
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip() or None
    password = os.getenv("SMTP_PASSWORD", "").strip() or None
    from_email = os.getenv("SMTP_FROM_EMAIL", "").strip() or username
    from_name = os.getenv("SMTP_FROM_NAME", "Ghana Climate Atlas").strip()
    use_tls = _env_bool("SMTP_USE_TLS", True)
    default_port = 587 if use_tls else 25

    try:
        port = int(os.getenv("SMTP_PORT", str(default_port)))
    except ValueError:
        port = default_port

    if not host:
        raise SMTPConfigurationError("SMTP email delivery is not configured")
    if not from_email:
        raise SMTPConfigurationError("SMTP sender is not configured")

    return SMTPConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        from_email=from_email,
        from_name=from_name or "Ghana Climate Atlas",
        use_tls=use_tls,
    )


def _format_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value or "Not specified")


def _build_confirmation_body(record: Mapping[str, Any]) -> str:
    submitted_at = record.get("submitted_at", "Not available")
    request_id = record.get("request_id", "Not available")

    return f"""Dear {record.get("full_name") or "Researcher"},

Thank you for submitting your climate data request through the Ghana Climate Atlas.

REQUEST DETAILS

Request ID: {request_id}
Submitted: {submitted_at}
Name: {record.get("full_name") or "Not specified"}
Email: {record.get("email") or "Not specified"}
Organization: {record.get("organization") or "Not specified"}

REQUESTED DATA

Purpose: {record.get("purpose") or "Not specified"}
Geographic area or districts: {record.get("geography") or "Not specified"}
Time period needed: {record.get("time_period") or "Not specified"}
Climate variables: {_format_list(record.get("climate_variables"))}
Scenarios: {_format_list(record.get("scenarios"))}
Preferred data format: {record.get("preferred_format") or "Not specified"}

PROCESSING

Your request has been received. The climate data team will review the requested package and follow up with download details.

If you need to modify this request, reply with your Request ID: {request_id}.

Best regards,
Ghana Climate Atlas Team
"""


def send_data_request_confirmation(record: Mapping[str, Any]) -> None:
    """Send a confirmation email for a saved data request.

    Raises RuntimeError or smtplib exceptions when configuration or delivery fails.
    The request router catches those errors and reports a non-fatal warning.
    """
    config = _load_smtp_config()
    recipient = str(record.get("email") or "").strip()
    if not recipient:
        raise RuntimeError("Request email address is missing")

    message = EmailMessage()
    message["Subject"] = f"Climate Data Request Confirmation - {record.get('request_id')}"
    message["From"] = f"{config.from_name} <{config.from_email}>"
    message["To"] = recipient
    message.set_content(_build_confirmation_body(record))

    with smtplib.SMTP(config.host, config.port, timeout=20) as smtp:
        smtp.ehlo()
        if config.use_tls:
            smtp.starttls()
            smtp.ehlo()
        if config.username and config.password:
            smtp.login(config.username, config.password)
        smtp.send_message(message)
