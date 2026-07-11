"""Always-on-top floating timer window."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QSettings, Qt
from PyQt6.QtGui import QAction, QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from .controller import TimerController
from .models import SIZE_PRESETS, TimerState, format_clock


class FloatingTimerWindow(QWidget):
    def __init__(self, controller: TimerController, open_frontend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._open_frontend = open_frontend
        self._state = TimerState(status="loading")
        self._drag_origin: QPoint | None = None
        self._settings = QSettings("CommandOS", "ActivityWatch")
        self._always_on_top = bool(self._settings.value("floating_timer/always_on_top", True, type=bool))
        self._size_preset = str(self._settings.value("floating_timer/size", "medium"))
        if self._size_preset not in SIZE_PRESETS:
            self._size_preset = "medium"
        self._title = QLabel("TIME LOG", self)
        self._clock = QLabel("00:00:00", self)
        self._status = QLabel("正在同步", self)
        self._configure_window()
        self._configure_layout()
        controller.state_changed.connect(self.apply_state)

    def _configure_window(self) -> None:
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._apply_size()
        stored = self._settings.value("floating_timer/position")
        if isinstance(stored, QPoint):
            self.move(stored)

    def _configure_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setObjectName("floating_timer_layout")
        layout.setSpacing(0)
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title)
        layout.addWidget(self._clock, 1)
        layout.addWidget(self._status)
        self._apply_size()

    def apply_state(self, state: TimerState) -> None:
        self._state = state
        session = state.selected
        if session is None:
            self._title.setText("TIME LOG")
            self._clock.setText("00:00:00")
            self._status.setText(state.message or "当前没有计时")
        else:
            self._title.setText(session.title.upper())
            self._clock.setText(format_clock(session.displayed_seconds()))
            self._status.setText("正在记录" if session.is_running else "已暂停")
        self.update()

    def set_size_preset(self, preset: str) -> None:
        if preset not in SIZE_PRESETS or preset == self._size_preset:
            return
        self._size_preset = preset
        self._settings.setValue("floating_timer/size", preset)
        self._apply_size()

    def _apply_size(self) -> None:
        width, height, clock_size, margin, text_size = SIZE_PRESETS[self._size_preset]
        self.setFixedSize(width, height)
        layout = self.layout()
        if isinstance(layout, QVBoxLayout):
            layout.setContentsMargins(margin, max(12, margin - 4), margin, max(24, margin + 8))
        self._title.setStyleSheet(f"font-size: {text_size}px; font-weight: 900; color: #181818;")
        self._clock.setStyleSheet(f"font-size: {clock_size}px; font-weight: 900; color: #181818;")
        self._status.setStyleSheet(f"font-size: {text_size}px; font-weight: 700; color: #555555;")

    def set_always_on_top(self, enabled: bool) -> None:
        if self._always_on_top == enabled:
            return
        self._always_on_top = enabled
        self._settings.setValue("floating_timer/always_on_top", enabled)
        self._configure_window()
        self.show()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        session = self._state.selected
        toggle = menu.addAction("暂停" if session and session.is_running else "继续")
        toggle.setEnabled(session is not None)
        toggle.triggered.connect(self._controller.toggle)
        finish = menu.addAction("完成计时")
        finish.setEnabled(session is not None)
        finish.triggered.connect(self._controller.finish)
        if len(self._state.sessions) > 1:
            sessions_menu = menu.addMenu("切换计时")
            for item in self._state.sessions:
                action = sessions_menu.addAction(item.title)
                action.setCheckable(True)
                action.setChecked(item.session_id == self._state.selected_session_id)
                action.triggered.connect(lambda _checked=False, session_id=item.session_id: self._controller.select(session_id))
        menu.addSeparator()
        menu.addAction("打开 Time Log", self._open_frontend)
        size_menu = menu.addMenu("尺寸")
        for preset, label in (("small", "小"), ("medium", "中"), ("large", "大")):
            action = size_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(preset == self._size_preset)
            action.triggered.connect(lambda _checked=False, value=preset: self.set_size_preset(value))
        topmost = QAction("始终置顶", menu)
        topmost.setCheckable(True)
        topmost.setChecked(self._always_on_top)
        topmost.toggled.connect(self.set_always_on_top)
        menu.addAction(topmost)
        menu.addAction("隐藏悬浮窗", self.hide)
        menu.exec(event.globalPos())

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shadow = self.rect().adjusted(10, 10, -2, -2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#181818"))
        painter.drawRoundedRect(shadow, 8, 8)
        card = self.rect().adjusted(2, 2, -10, -10)
        painter.setPen(QPen(QColor("#181818"), 3))
        painter.setBrush(QColor("#fff8e8"))
        painter.drawRoundedRect(card, 8, 8)
        session = self._state.selected
        if session:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(session.accent))
            painter.drawRoundedRect(card.left() + 12, card.bottom() - 6, card.width() - 24, 3, 1, 1)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            self._settings.setValue("floating_timer/position", self.pos())

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
