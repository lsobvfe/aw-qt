"""Always-on-top floating timer window."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QByteArray, QPoint, QSettings, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PyQt6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from .controller import TimerController
from .models import TimerState, format_clock
from .ui.dialogs import (
    choose_activity,
    choose_custom_tag,
    choose_tags,
    prompt_new_tag,
)
from .ui.leisure_dialog import edit_leisure_settings
from .ui.theme import (
    COLOR_MODES,
    LEISURE_TEXT_COLOR,
    ThemeManager,
    leisure_card_color,
)


MINIMUM_TIMER_SIZE = (220, 96)
DEFAULT_TIMER_SIZE = (420, 156)
CARD_INSET = 2
SHADOW_INSET = 10
RESIZE_HANDLE_WIDTH = 8
CLOCK_FONT_FAMILIES = {
    "darwin": "Helvetica Neue",
    "linux": "DejaVu Sans",
    "win32": "Bahnschrift",
}


def clock_font_family() -> str:
    try:
        family = CLOCK_FONT_FAMILIES[sys.platform]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported desktop platform: {sys.platform}") from exc
    if family not in QFontDatabase.families():
        raise RuntimeError(f"Required timer clock font is not installed: {family}")
    return family


class ElidedLabel(QLabel):
    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        text = QFontMetrics(self.font()).elidedText(
            self.text(),
            Qt.TextElideMode.ElideRight,
            max(0, self.width()),
        )
        painter.drawText(self.rect(), int(self.alignment()), text)


class FloatingTimerWindow(QWidget):
    def __init__(
        self,
        controller: TimerController,
        open_time_log_view,
        theme: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._open_time_log_view = open_time_log_view
        self._theme = theme
        self._state = TimerState(status="loading")
        self._drag_origin: QPoint | None = None
        self._settings = QSettings("CommandOS", "ActivityWatch")
        self._always_on_top = bool(self._settings.value("floating_timer/always_on_top", True, type=bool))
        self._clock = QLabel("00:00:00", self)
        self._footer = ElidedLabel("正在同步", self)
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(250)
        self._geometry_timer.timeout.connect(self._save_geometry)
        self._configure_window()
        self._configure_layout()
        controller.state_changed.connect(self.apply_state)
        theme.changed.connect(self._apply_theme)

    def _configure_window(self) -> None:
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(*MINIMUM_TIMER_SIZE)
        stored = self._settings.value("floating_timer/geometry")
        restored = isinstance(stored, QByteArray) and self.restoreGeometry(stored)
        if not restored:
            self.resize(*DEFAULT_TIMER_SIZE)

    def _configure_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setObjectName("floating_timer_layout")
        layout.setSpacing(0)
        self._clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clock.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._footer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self._clock, 1)
        layout.addWidget(self._footer)
        self._apply_metrics()

    def apply_state(self, state: TimerState) -> None:
        self._state = state
        leisure = state.leisure
        if leisure is not None and leisure.session is not None:
            remaining = leisure.session.displayed_seconds()
            self._clock.setText(format_clock(remaining))
            prefix = "" if leisure.session.is_running else "已暂停  ·  "
            if leisure.session.display_source == "fixed":
                end_text = leisure.session.ends_at.astimezone().strftime("%H:%M")
                self._footer.setText(
                    f"{prefix}固定闲暇  ·  至 {end_text}"
                )
            else:
                self._footer.setText(
                    f"{prefix}积累闲暇  ·  余额 "
                    f"{format_clock(leisure.balance_seconds)}"
                )
            self._footer.setToolTip(self._footer.text())
            self._apply_theme()
            self.update()
            return
        session = state.selected
        if session is None:
            self._clock.setText("00:00:00")
            self._footer.setText(state.message or "当前没有计时")
        else:
            self._clock.setText(format_clock(session.displayed_seconds()))
            prefix = "" if session.is_running else "已暂停  ·  "
            self._footer.setText(f"{prefix}{session.footer_text}")
        self._footer.setToolTip(self._footer.text())
        self._apply_theme()
        self.update()

    def _apply_metrics(self) -> None:
        width = max(1, self.width())
        height = max(1, self.height())
        margin = max(10, min(28, round(min(width, height) * 0.08)))
        footer_size = max(10, min(18, round(height * 0.085)))
        clock_size = max(
            32,
            min(
                round(height * 0.52),
                round((width - margin * 2) / 5.3),
            ),
        )
        layout = self.layout()
        if isinstance(layout, QVBoxLayout):
            layout.setContentsMargins(margin, margin, margin, max(14, margin))
        clock_font = QFont(clock_font_family())
        clock_font.setPixelSize(clock_size)
        clock_font.setWeight(QFont.Weight.DemiBold)
        clock_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        self._clock.setFont(clock_font)
        footer_font = QFont(self.font())
        footer_font.setPixelSize(footer_size)
        footer_font.setWeight(QFont.Weight.DemiBold)
        self._footer.setFont(footer_font)
        self._apply_theme()

    def _apply_theme(self, _resolved: str = "") -> None:
        leisure = self._state.leisure
        if leisure is not None and leisure.session is not None:
            self._clock.setStyleSheet(f"color: {LEISURE_TEXT_COLOR};")
            self._footer.setStyleSheet(f"color: {LEISURE_TEXT_COLOR};")
        else:
            palette = self._theme.timer_palette
            self._clock.setStyleSheet(f"color: {palette.clock};")
            self._footer.setStyleSheet(f"color: {palette.footer};")
        self.update()

    def set_always_on_top(self, enabled: bool) -> None:
        if self._always_on_top == enabled:
            return
        self._always_on_top = enabled
        self._settings.setValue("floating_timer/always_on_top", enabled)
        geometry = self.saveGeometry()
        self._configure_window()
        self.restoreGeometry(geometry)
        self.show()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        session = self._state.selected
        leisure = self._state.leisure
        leisure_active = leisure is not None and leisure.session is not None
        if leisure_active:
            toggle_leisure = menu.addAction(
                (
                    "暂停闲暇时刻"
                    if leisure.session.is_running
                    else "继续闲暇时刻"
                ),
                self._controller.toggle_leisure,
            )
            toggle_leisure.setEnabled(True)
            menu.addAction("结束闲暇时刻", self._controller.stop_leisure)
        else:
            start_leisure = menu.addAction(
                "进入闲暇时刻",
                self._controller.start_leisure,
            )
            start_leisure.setEnabled(
                leisure is not None and leisure.available
            )
        configure_leisure = menu.addAction(
            "配置闲暇时刻...",
            self._configure_leisure,
        )
        configure_leisure.setEnabled(not leisure_active)
        menu.addSeparator()
        toggle = menu.addAction("暂停" if session and session.is_running else "继续")
        toggle.setEnabled(session is not None and not leisure_active)
        toggle.triggered.connect(self._controller.toggle)
        finish = menu.addAction("完成计时")
        finish.setEnabled(session is not None and not leisure_active)
        finish.triggered.connect(self._controller.finish)
        if len(self._state.sessions) > 1:
            sessions_menu = menu.addMenu("切换计时")
            for item in self._state.sessions:
                action = sessions_menu.addAction(item.title)
                action.setCheckable(True)
                action.setChecked(item.session_id == self._state.selected_session_id)
                action.triggered.connect(lambda _checked=False, session_id=item.session_id: self._controller.select(session_id))
        menu.addSeparator()
        start_event = menu.addAction("开始新事件...")
        start_event.setEnabled(bool(self._state.activities) and not leisure_active)
        start_event.triggered.connect(self._start_activity)
        change_event = menu.addAction("切换当前事件...")
        change_event.setEnabled(
            session is not None
            and bool(self._state.activities)
            and not leisure_active
        )
        change_event.triggered.connect(self._change_activity)
        edit_tags = menu.addAction("编辑当前标签...")
        edit_tags.setEnabled(
            session is not None
            and bool(self._state.tags)
            and not leisure_active
        )
        edit_tags.triggered.connect(self._edit_tags)
        menu.addAction("新建标签...", self._create_tag)
        delete_tag = menu.addAction("删除自定义标签...", self._delete_tag)
        delete_tag.setEnabled(any(not tag.is_default for tag in self._state.tags))
        menu.addSeparator()
        menu.addAction(
            "打开 Time Log 启动器",
            lambda: self._open_time_log_view("launcher"),
        )
        menu.addAction(
            "打开今日编辑",
            lambda: self._open_time_log_view("day"),
        )
        menu.addAction(
            "打开统计概览",
            lambda: self._open_time_log_view("overview"),
        )
        theme_menu = menu.addMenu("外观")
        theme_group = QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        theme_labels = {"system": "跟随系统", "light": "浅色", "dark": "暗色"}
        for mode in COLOR_MODES:
            action = theme_menu.addAction(theme_labels[mode])
            action.setCheckable(True)
            action.setChecked(self._theme.mode == mode)
            action.triggered.connect(
                lambda _checked=False, value=mode: self._theme.set_mode(value)
            )
            theme_group.addAction(action)
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
        palette = self._theme.timer_palette
        leisure = self._state.leisure
        leisure_session = leisure.session if leisure is not None else None
        shadow = self.rect().adjusted(
            SHADOW_INSET,
            SHADOW_INSET,
            -CARD_INSET,
            -CARD_INSET,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette.shadow))
        painter.drawRoundedRect(shadow, 8, 8)
        card = self.rect().adjusted(
            CARD_INSET,
            CARD_INSET,
            -SHADOW_INSET,
            -SHADOW_INSET,
        )
        if leisure_session is not None:
            card_color = leisure_card_color(
                leisure_session.displayed_seconds()
            )
            painter.setPen(QPen(QColor(LEISURE_TEXT_COLOR), 3))
            painter.setBrush(QColor(card_color))
        else:
            painter.setPen(QPen(QColor(palette.border), 3))
            painter.setBrush(QColor(palette.card))
        painter.drawRoundedRect(card, 8, 8)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._resize_edges(event.position().toPoint())
            handle = self.windowHandle()
            if edges and handle is not None and handle.startSystemResize(edges):
                self._drag_origin = None
                event.accept()
                return
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            return
        self._apply_resize_cursor(self._resize_edges(event.position().toPoint()))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            self._schedule_geometry_save()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = None
            leisure = self._state.leisure
            if leisure is not None and leisure.session is not None:
                self._controller.stop_leisure()
            else:
                self._controller.toggle()
            event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_metrics()
        self._schedule_geometry_save()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()

    def _start_activity(self) -> None:
        activity_id = choose_activity(self._state.activities, "开始新事件", self)
        if activity_id:
            self._controller.start_activity(activity_id)

    def _change_activity(self) -> None:
        activity_id = choose_activity(self._state.activities, "切换当前事件", self)
        if activity_id:
            self._controller.change_activity(activity_id)

    def _edit_tags(self) -> None:
        session = self._state.selected
        if session is None:
            return
        selected = choose_tags(self._state.tags, session.tags, self)
        if selected is not None:
            self._controller.update_tags(selected)

    def _create_tag(self) -> None:
        name = prompt_new_tag(self)
        if name:
            self._controller.create_tag(name)

    def _delete_tag(self) -> None:
        name = choose_custom_tag(self._state.tags, self)
        if name:
            self._controller.delete_tag(name)

    def _configure_leisure(self) -> None:
        leisure = self._state.leisure
        if leisure is not None and leisure.session is not None:
            return
        payload = edit_leisure_settings(
            leisure.policy if leisure is not None else None,
            self._state.activities,
            self._state.tags,
            self,
        )
        if payload is not None:
            self._controller.update_leisure_settings(payload)

    def _resize_edges(self, position: QPoint):
        edges = Qt.Edge(0)
        if position.x() <= CARD_INSET + RESIZE_HANDLE_WIDTH:
            edges |= Qt.Edge.LeftEdge
        elif position.x() >= self.width() - SHADOW_INSET - RESIZE_HANDLE_WIDTH:
            edges |= Qt.Edge.RightEdge
        if position.y() <= CARD_INSET + RESIZE_HANDLE_WIDTH:
            edges |= Qt.Edge.TopEdge
        elif position.y() >= self.height() - SHADOW_INSET - RESIZE_HANDLE_WIDTH:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _apply_resize_cursor(self, edges) -> None:
        if edges in (
            Qt.Edge.LeftEdge | Qt.Edge.TopEdge,
            Qt.Edge.RightEdge | Qt.Edge.BottomEdge,
        ):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (
            Qt.Edge.RightEdge | Qt.Edge.TopEdge,
            Qt.Edge.LeftEdge | Qt.Edge.BottomEdge,
        ):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def _schedule_geometry_save(self) -> None:
        if not self._geometry_timer.isActive():
            self._geometry_timer.start()

    def _save_geometry(self) -> None:
        self._settings.setValue("floating_timer/geometry", self.saveGeometry())
