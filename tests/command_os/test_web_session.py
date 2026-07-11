import base64
import json
from datetime import datetime, timezone

import pytest
from aw_client.desktop_session import DesktopSession

from aw_qt.command_os.ui.web_session import time_log_url, web_session_payload


def _token(payload: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


def test_web_session_uses_desktop_identity_and_expiry_contract() -> None:
    access_expiry = datetime(2026, 7, 11, 12, tzinfo=timezone.utc)
    refresh_expiry = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    session = DesktopSession(
        access_token=_token(
            {
                "account_id": "account-1",
                "sub": "user-1",
                "workspace_id": "workspace-1",
                "roles": ["member"],
                "scope": "command:read command:write",
            }
        ),
        refresh_token="refresh-token",
        access_expires_at=access_expiry,
        refresh_expires_at=refresh_expiry,
    )

    payload = web_session_payload(session)

    assert payload["user"] | {
        "created_at": "",
        "updated_at": "",
    } == {
        "account_id": "account-1",
        "user_id": "user-1",
        "workspace_id": "workspace-1",
        "username": "user-1",
        "roles": ["member"],
        "scopes": ["command:read", "command:write"],
        "created_at": "",
        "updated_at": "",
    }
    assert payload["access_expires_at"] == access_expiry.isoformat()
    assert payload["refresh_expires_at"] == refresh_expiry.isoformat()


def test_time_log_url_accepts_only_declared_views_and_absolute_http_origin() -> None:
    assert time_log_url("https://command.example/base", "overview") == (
        "https://command.example/workbench/time-log/overview"
    )
    with pytest.raises(ValueError, match="Unsupported Time Log view"):
        time_log_url("https://command.example", "missing")
    with pytest.raises(ValueError, match="absolute HTTP URL"):
        time_log_url("file:///tmp/index.html", "launcher")
