"""Shared appearance state for the native timer and embedded workbench."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QPalette


COLOR_MODES = ("system", "light", "dark")


@dataclass(frozen=True)
class TimerPalette:
    shadow: str
    border: str
    card: str
    clock: str
    footer: str


TIMER_PALETTES = {
    "light": TimerPalette(
        shadow="#181818",
        border="#181818",
        card="#fff8e8",
        clock="#181818",
        footer="#454545",
    ),
    "dark": TimerPalette(
        shadow="#050505",
        border="#f4ead6",
        card="#20201d",
        clock="#fff8e8",
        footer="#c9c0af",
    ),
}


class ThemeManager(QObject):
    changed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings("CommandOS", "ActivityWatch")
        self._mode = str(self._settings.value("appearance/color_mode", "system"))
        if self._mode not in COLOR_MODES:
            raise RuntimeError(f"Unsupported stored color mode: {self._mode}")
        self._resolved = self._resolve()
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            self._system_color_scheme_changed
        )

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def resolved(self) -> str:
        return self._resolved

    @property
    def timer_palette(self) -> TimerPalette:
        return TIMER_PALETTES[self._resolved]

    def set_mode(self, mode: str) -> None:
        if mode not in COLOR_MODES:
            raise ValueError(f"Unsupported color mode: {mode}")
        if self._mode == mode:
            return
        self._mode = mode
        self._settings.setValue("appearance/color_mode", mode)
        self._publish_resolved(force=True)

    def _system_color_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._mode == "system":
            self._publish_resolved()

    def _publish_resolved(self, *, force: bool = False) -> None:
        resolved = self._resolve()
        if resolved == self._resolved and not force:
            return
        self._resolved = resolved
        self.changed.emit(resolved)

    def _resolve(self) -> str:
        if self._mode != "system":
            return self._mode
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
        window_color = QGuiApplication.palette().color(QPalette.ColorRole.Window)
        return "dark" if window_color.lightness() < 128 else "light"
