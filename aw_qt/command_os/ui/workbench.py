"""Qt-hosted canonical Command OS Web Time Log workbench."""

from __future__ import annotations

import json
import webbrowser
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from aw_client.desktop_session import DesktopSession
from PyQt6.QtCore import QByteArray, QSettings, QStandardPaths, QUrl
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow

from .theme import ThemeManager
from .web_session import time_log_url, web_session_payload


class _TimeLogPage(QWebEnginePage):
    def __init__(
        self,
        allowed_origin: str,
        profile: QWebEngineProfile,
        parent=None,
    ) -> None:
        super().__init__(profile, parent)
        self._allowed_origin = allowed_origin

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame:
            target = url.toString()
            if target == "about:blank":
                return super().acceptNavigationRequest(
                    url, navigation_type, is_main_frame
                )
            if _origin(target) != self._allowed_origin:
                webbrowser.open(target)
                return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)


class WebTimeLogWindow(QMainWindow):
    def __init__(
        self,
        base_url: str,
        session_provider: Callable[[], DesktopSession | None],
        theme: ThemeManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._origin = _origin(base_url)
        self._session_provider = session_provider
        self._theme = theme
        self._settings = QSettings("CommandOS", "ActivityWatch")
        self._script: QWebEngineScript | None = None
        self.setWindowTitle("Time Log")
        self.setMinimumSize(880, 620)
        self._profile = QWebEngineProfile("CommandOSTimeLog", self)
        storage_root = (
            Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
            / "webengine"
            / "time-log"
        )
        storage_root.mkdir(parents=True, exist_ok=True)
        self._profile.setPersistentStoragePath(str(storage_root / "storage"))
        self._profile.setCachePath(str(storage_root / "cache"))
        self._page = _TimeLogPage(self._origin, self._profile, self)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)
        stored = self._settings.value("time_log_workbench/geometry")
        restored = isinstance(stored, QByteArray) and self.restoreGeometry(stored)
        if not restored:
            self.resize(1280, 840)
        theme.changed.connect(self._theme_changed)

    def open_view(self, view: str) -> None:
        session = self._session_provider()
        if session is None:
            raise RuntimeError("Desktop authorization is required")
        self._install_bootstrap_script(session)
        target = QUrl(time_log_url(self._base_url, view))
        if self._view.url() == target:
            self._view.reload()
        else:
            self._view.setUrl(target)
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_session(self) -> None:
        session = self._session_provider()
        if session is None:
            return
        self._install_bootstrap_script(session)
        if self.isVisible():
            self._view.reload()

    def closeEvent(self, event) -> None:
        self._settings.setValue("time_log_workbench/geometry", self.saveGeometry())
        event.ignore()
        self.hide()

    def _install_bootstrap_script(self, session: DesktopSession) -> None:
        if self._script is not None:
            self._page.scripts().remove(self._script)
        serialized_session = json.dumps(
            web_session_payload(session),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        source = f"""
(() => {{
  if (window.location.origin !== {json.dumps(self._origin)}) return;
  localStorage.setItem("command-os.auth.session.v1", {json.dumps(serialized_session)});
  localStorage.setItem("command-os-color-mode", {json.dumps(self._theme.mode)});
}})();
"""
        script = QWebEngineScript()
        script.setName("command-os-time-log-bootstrap")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(source)
        self._page.scripts().insert(script)
        self._script = script

    def _theme_changed(self, _resolved: str) -> None:
        session = self._session_provider()
        if session is None:
            return
        self._install_bootstrap_script(session)
        if self.isVisible():
            self._view.reload()


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Workbench URL must be an absolute HTTP URL")
    return f"{parsed.scheme}://{parsed.netloc}"
