from urllib.parse import parse_qs, urlparse

import tomlkit

from aw_qt.command_os.config import DesktopConfig, write_aw_client_config
from aw_qt.command_os.desktop import _DesktopAuthorization, _code_challenge


def test_pkce_s256_matches_rfc_7636_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert _code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_desktop_authorization_requires_pkce_and_stable_device_identity(monkeypatch) -> None:
    opened = []
    authorization = _DesktopAuthorization(
        login_url="https://command-os.example.test/login",
        command_os_url="https://command-os.example.test",
        device_id="activitywatch_device",
        device_name="ActivityWatch test",
    )
    monkeypatch.setattr(
        authorization,
        "_start",
        lambda: "http://127.0.0.1:18111/callback",
    )
    monkeypatch.setattr(
        "aw_qt.command_os.desktop.webbrowser.open",
        opened.append,
    )

    authorization.open()

    query = parse_qs(urlparse(opened[0]).query)
    assert query["redirect_uri"] == ["http://127.0.0.1:18111/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [_code_challenge(authorization.code_verifier)]
    assert query["device_id"] == ["activitywatch_device"]
    assert query["device_name"] == ["ActivityWatch test"]
    assert query["state"] == [authorization.state]


def test_aw_client_config_preserves_explicit_protocol(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "aw_core.dirs.get_config_dir",
        lambda _name: str(tmp_path),
    )

    write_aw_client_config("https://command-os.example.test/api/0")

    document = tomlkit.parse((tmp_path / "aw-client.toml").read_text(encoding="utf-8"))
    assert document["server"] == {
        "protocol": "https",
        "hostname": "command-os.example.test",
        "port": "443",
    }
    assert document["client"]["commit_interval"] == 10
    assert "auth" not in document


def test_desktop_config_requires_explicit_managed_modules() -> None:
    config = DesktopConfig.create(
        dashboard_url="https://command-os.example.test/activitywatch",
        activitywatch_api_url="https://command-os.example.test/api/0",
        login_url="https://command-os.example.test/login",
        command_os_url="https://command-os.example.test",
        time_log_url="https://command-os.example.test/time-log",
        managed_modules=("aw-watcher-window", "aw-watcher-afk"),
    )

    assert config.managed_modules == ("aw-watcher-window", "aw-watcher-afk")
