"""Composition root for Command OS desktop behavior."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import socket
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from aw_client.desktop_session import DesktopSession, DesktopSessionStore
from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal

from .client import CommandClient
from .config import DesktopConfig, write_aw_client_config
from .controller import TimerController
from .session_client import SessionClient
from .ui.theme import ThemeManager
from .ui.web_session import TIME_LOG_PATHS
from .ui.workbench import WebTimeLogWindow
from .window import FloatingTimerWindow


SESSION_REFRESH_MARGIN = timedelta(minutes=2)
SESSION_REFRESH_RETRY_MS = 30_000
SESSION_REFRESH_MAX_TIMER_MS = 24 * 60 * 60 * 1000

logger = logging.getLogger(__name__)


class CommandOSDesktop(QObject):
    authorization_completed = pyqtSignal()
    authorization_failed = pyqtSignal(str)
    authorization_session_received = pyqtSignal(object)

    def __init__(self, config: DesktopConfig, manager, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.manager = manager
        self.credentials = _credential_store(config.activitywatch_api_url)
        self._session: DesktopSession | None = None
        self._credential_error = ""
        try:
            self._session = self.credentials.load()
        except RuntimeError as exc:
            self._credential_error = str(exc)
        self._authorization_active = False
        self._authorization: _DesktopAuthorization | None = None
        self._pending_time_log_view = ""
        self.client = CommandClient(config.command_os_url, self.access_token, self)
        self.session_client = SessionClient(config.command_os_url, self)
        self.controller = TimerController(self.client, self)
        self.theme = ThemeManager(self)
        self.workbench = WebTimeLogWindow(
            config.time_log_url,
            lambda: self._session,
            self.theme,
            parent,
        )
        self.window = FloatingTimerWindow(
            self.controller,
            self.open_time_log,
            self.theme,
        )
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_if_due)
        self.controller.authorization_required.connect(self.authorize)
        self.client.unauthorized.connect(self.refresh_session)
        self.session_client.refreshed.connect(self._store_refreshed_session)
        self.session_client.authorization_required.connect(self._invalidate_session)
        self.session_client.failed.connect(self._session_refresh_failed)
        self.authorization_session_received.connect(self._store_authorized_session)
        self.authorization_completed.connect(self._authorization_ready)
        self.authorization_failed.connect(self._authorization_failed)

    def start(self) -> None:
        self.controller.start()
        self.window.show()
        if self._credential_error:
            self.controller.report_error(self._credential_error)
            self.authorize()
            return
        if self._session is None:
            self.authorize()
            return
        self._ensure_managed_modules_running()
        self._schedule_refresh()

    def show_timer(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.controller.refresh()

    def open_dashboard(self) -> None:
        self._open(self._render_dashboard_url())

    def open_time_log(self, view: str = "launcher") -> None:
        if view not in TIME_LOG_PATHS:
            raise ValueError(f"Unsupported Time Log view: {view}")
        if self._session is None:
            self._pending_time_log_view = view
            self.authorize()
            return
        self.workbench.open_view(view)

    def open_api(self) -> None:
        self._open(self.config.activitywatch_api_url)

    def authorize(self) -> None:
        if self._authorization_active:
            return
        self._authorization_active = True
        self._authorization = _DesktopAuthorization(
            login_url=self.config.login_url,
            command_os_url=self.config.command_os_url,
            device_id=self._device_id(),
            device_name=f"ActivityWatch on {socket.gethostname()}",
        )
        self._authorization.completed = self.authorization_session_received.emit
        self._authorization.failed = self.authorization_failed.emit
        self._authorization.open()

    def access_token(self) -> str:
        return self._session.access_token if self._session else ""

    def refresh_session(self) -> None:
        if self._session is None:
            self.authorize()
            return
        self.session_client.refresh(self._session.refresh_token)

    def _store_authorized_session(self, session: dict[str, Any]) -> None:
        if self._store_session(session):
            self.authorization_completed.emit()

    def _store_refreshed_session(self, session: dict[str, Any]) -> None:
        if self._store_session(session):
            self.workbench.refresh_session()
            self.controller.refresh()

    def _store_session(self, session: dict[str, Any]) -> bool:
        try:
            previous_access_token = self._session.access_token if self._session else ""
            self._session = self.credentials.save(session)
        except RuntimeError as exc:
            self._authorization_active = False
            self.controller.report_error(str(exc))
            return False
        write_aw_client_config(self.config.activitywatch_api_url)
        if previous_access_token:
            self._restart_managed_modules()
        else:
            self._ensure_managed_modules_running()
        self._schedule_refresh()
        return True

    def _authorization_ready(self) -> None:
        self._authorization_active = False
        self._authorization = None
        self.controller.refresh()
        self.show_timer()
        if self._pending_time_log_view:
            view = self._pending_time_log_view
            self._pending_time_log_view = ""
            self.workbench.open_view(view)

    def _authorization_failed(self, message: str) -> None:
        self._authorization_active = False
        self._authorization = None
        self.controller.report_error(message)

    def _schedule_refresh(self) -> None:
        if self._session is None:
            return
        remaining = self._session.access_expires_at - datetime.now(timezone.utc)
        delay = max(timedelta(seconds=1), remaining - SESSION_REFRESH_MARGIN)
        delay_ms = min(int(delay.total_seconds() * 1000), SESSION_REFRESH_MAX_TIMER_MS)
        self._refresh_timer.start(delay_ms)

    def _refresh_if_due(self) -> None:
        if self._session is None:
            self.authorize()
            return
        remaining = self._session.access_expires_at - datetime.now(timezone.utc)
        if remaining > SESSION_REFRESH_MARGIN:
            self._schedule_refresh()
            return
        self.refresh_session()

    def _session_refresh_failed(self, message: str) -> None:
        self.controller.report_error(message)
        self._refresh_timer.start(SESSION_REFRESH_RETRY_MS)

    def _invalidate_session(self) -> None:
        self.credentials.delete()
        self._session = None
        self._stop_managed_modules()
        self.authorize()

    def _ensure_managed_modules_running(self) -> None:
        for name in self.config.managed_modules:
            module = next((item for item in self.manager.modules if item.name == name), None)
            if module is None:
                self.controller.report_error(f"Required ActivityWatch module is missing: {name}")
                continue
            if not module.is_alive():
                self.manager.start(name)

    def _restart_managed_modules(self) -> None:
        self._stop_managed_modules()
        self._ensure_managed_modules_running()

    def _stop_managed_modules(self) -> None:
        for name in self.config.managed_modules:
            module = next((item for item in self.manager.modules if item.name == name), None)
            if module is not None and module.is_alive():
                self.manager.stop(name)

    @staticmethod
    def _device_id() -> str:
        settings = QSettings("CommandOS", "ActivityWatch")
        value = str(settings.value("desktop/device_id", "") or "").strip()
        if value:
            return value
        value = f"activitywatch_{uuid4().hex}"
        settings.setValue("desktop/device_id", value)
        return value

    def _render_dashboard_url(self) -> str:
        return (
            self.config.dashboard_url
            .replace("__HOSTNAME__", quote(socket.gethostname(), safe=""))
            .replace("__DATE__", datetime.now().date().isoformat())
        )

    @staticmethod
    def _open(url: str) -> None:
        webbrowser.open(url)


class _DesktopAuthorization:
    def __init__(
        self,
        *,
        login_url: str,
        command_os_url: str,
        device_id: str,
        device_name: str,
    ) -> None:
        self.login_url = login_url
        self.command_os_url = command_os_url
        self.device_id = device_id
        self.device_name = device_name
        self.state = secrets.token_urlsafe(32)
        self.code_verifier = secrets.token_urlsafe(64)
        self.server: ThreadingHTTPServer | None = None
        self.redirect_uri = ""
        self.completed = lambda _session: None
        self.failed = lambda _message: None

    def open(self) -> None:
        self.redirect_uri = self._start()
        origin = _origin(self.login_url)
        query = urlencode(
            {
                "redirect_uri": self.redirect_uri,
                "state": self.state,
                "code_challenge": _code_challenge(self.code_verifier),
                "code_challenge_method": "S256",
                "device_id": self.device_id,
                "device_name": self.device_name,
            }
        )
        webbrowser.open(f"{origin}/auth/desktop-authorize?{query}")

    def _start(self) -> str:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:
                try:
                    owner._handle(self)
                finally:
                    threading.Thread(target=owner.close, daemon=True).start()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = int(self.server.server_address[1])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{port}/callback"

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        params = parse_qs(urlparse(handler.path).query)
        if params.get("state", [""])[0] != self.state:
            self._fail(handler, 400, "Desktop authorization state is invalid.")
            return
        code = params.get("code", [""])[0]
        if not code:
            self._fail(handler, 400, "Desktop authorization code is missing.")
            return
        request = Request(
            f"{_origin(self.command_os_url)}/auth/desktop-token",
            data=json.dumps(
                {
                    "code": code,
                    "code_verifier": self.code_verifier,
                    "redirect_uri": self.redirect_uri,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                session = json.loads(response.read().decode("utf-8"))
            self.completed(session)
        except Exception:
            logger.exception("Command OS desktop authorization exchange failed")
            self._fail(handler, 500, "Command OS desktop authorization exchange failed.")
            return
        _write_response(handler, 200, "Command OS desktop authorization complete. You can close this tab.")

    def _fail(self, handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
        self.failed(message)
        _write_response(handler, status, message)

    def close(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _credential_store(activitywatch_api_url: str) -> DesktopSessionStore:
    parsed = urlparse(activitywatch_api_url)
    if parsed.hostname is None:
        raise ValueError("activitywatch_api_url must include a hostname")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return DesktopSessionStore(parsed.hostname, port)


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _write_response(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    body = f"<!doctype html><meta charset='utf-8'><p>{message}</p>".encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
