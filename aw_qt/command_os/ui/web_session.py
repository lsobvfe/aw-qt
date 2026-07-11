"""Canonical Web workbench bootstrap data derived from a desktop session."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from aw_client.desktop_session import DesktopSession


TIME_LOG_PATHS = {
    "launcher": "/workbench/time-log",
    "day": "/workbench/time-log/day",
    "overview": "/workbench/time-log/overview",
}


def time_log_url(base_url: str, view: str) -> str:
    try:
        path = TIME_LOG_PATHS[view]
    except KeyError as exc:
        raise ValueError(f"Unsupported Time Log view: {view}") from exc
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Time Log base URL must be an absolute HTTP URL")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def web_session_payload(session: DesktopSession) -> dict[str, Any]:
    claims = _access_token_claims(session.access_token)
    account_id = _required_claim(claims, "account_id")
    user_id = _required_claim(claims, "sub")
    workspace_id = _required_claim(claims, "workspace_id")
    roles = _string_list_claim(claims, "roles")
    scopes = _required_claim(claims, "scope").split()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "user": {
            "account_id": account_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "username": user_id,
            "roles": roles,
            "scopes": scopes,
            "created_at": now,
            "updated_at": now,
        },
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "Bearer",
        "access_expires_at": session.access_expires_at.isoformat(),
        "refresh_expires_at": session.refresh_expires_at.isoformat(),
    }


def _access_token_claims(token: str) -> dict[str, Any]:
    segments = token.split(".")
    if len(segments) != 3:
        raise RuntimeError("Desktop access token must be a signed JWT")
    try:
        encoded = segments[1] + "=" * (-len(segments[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Desktop access token payload is invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Desktop access token payload must be an object")
    return payload


def _required_claim(claims: dict[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Desktop access token claim is invalid: {name}")
    return value.strip()


def _string_list_claim(claims: dict[str, Any], name: str) -> list[str]:
    value = claims.get(name)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise RuntimeError(f"Desktop access token claim is invalid: {name}")
    return [item.strip() for item in value]
