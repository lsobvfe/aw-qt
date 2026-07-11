"""Validated desktop configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

import tomlkit


@dataclass(frozen=True)
class DesktopConfig:
    dashboard_url: str
    activitywatch_api_url: str
    login_url: str
    command_os_url: str
    time_log_url: str
    managed_modules: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        dashboard_url: str,
        activitywatch_api_url: str,
        login_url: str,
        command_os_url: str,
        time_log_url: str,
        managed_modules: tuple[str, ...],
    ) -> "DesktopConfig":
        values = {
            "dashboard_url": dashboard_url,
            "activitywatch_api_url": activitywatch_api_url,
            "login_url": login_url,
            "command_os_url": command_os_url,
            "time_log_url": time_log_url,
        }
        normalized = {key: _absolute_url(value, key) for key, value in values.items()}
        modules = tuple(dict.fromkeys(str(item).strip() for item in managed_modules if str(item).strip()))
        if not modules:
            raise ValueError("managed_modules must contain at least one module")
        return cls(**normalized, managed_modules=modules)


def _absolute_url(value: str, field: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute HTTP URL")
    return normalized


def write_aw_client_config(activitywatch_api_url: str) -> None:
    from aw_core import dirs

    parsed = urlparse(_absolute_url(activitywatch_api_url, "activitywatch_api_url"))
    path = Path(dirs.get_config_dir("aw-client")) / "aw-client.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    document = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()
    server = document.get("server")
    if not isinstance(server, dict):
        server = tomlkit.table()
        document["server"] = server
    server["protocol"] = parsed.scheme
    server["hostname"] = parsed.hostname
    server["port"] = str(parsed.port or (443 if parsed.scheme == "https" else 80))
    client = document.get("client")
    if not isinstance(client, dict):
        client = tomlkit.table()
        document["client"] = client
    client["commit_interval"] = 10
    document.pop("auth", None)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(tomlkit.dumps(document))
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)
