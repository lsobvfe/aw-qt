import sys

from PyQt6.QtCore import QObject, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from aw_qt.command_os.models import parse_timer_state
from aw_qt.command_os.ui.theme import ThemeManager
from aw_qt.command_os.window import (
    CARD_INSET,
    CLOCK_FONT_FAMILIES,
    FloatingTimerWindow,
    MINIMUM_TIMER_SIZE,
    SHADOW_INSET,
)


class FakeController(QObject):
    state_changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.toggle_count = 0

    def toggle(self) -> None:
        self.toggle_count += 1

    def finish(self) -> None:
        pass

    def select(self, _session_id: str) -> None:
        pass

    def start_activity(self, _activity_id: str) -> None:
        pass

    def change_activity(self, _activity_id: str) -> None:
        pass

    def update_tags(self, _tags: list[str]) -> None:
        pass

    def create_tag(self, _name: str) -> None:
        pass

    def delete_tag(self, _name: str) -> None:
        pass


def test_timer_window_is_freely_resizable_and_double_click_toggles() -> None:
    app = QApplication.instance() or QApplication([])
    controller = FakeController()
    theme = ThemeManager()
    window = FloatingTimerWindow(controller, lambda _view: None, theme)
    window.resize(520, 210)
    window.apply_state(
        parse_timer_state(
            {
                "active_sessions": [
                    {
                        "session_id": "session-1",
                        "state": "active",
                        "elapsed_seconds": 3723,
                        "entry": {
                            "title": "Architecture",
                            "label": "Architecture",
                            "bound_object": {"label": "Command OS"},
                            "tags": ["工作", "设计"],
                            "accent": "#69e36d",
                            "emoji": "◆",
                            "timer_mode": "countup",
                            "countdown_minutes": 25,
                            "pomodoro_work_minutes": 25,
                            "pomodoro_rest_minutes": 5,
                        },
                    }
                ],
                "activities": [],
                "tag_catalog": [
                    {"name": "工作", "is_default": True},
                    {"name": "设计", "is_default": False},
                ],
            }
        )
    )
    window.show()
    app.processEvents()

    assert window.minimumWidth() == MINIMUM_TIMER_SIZE[0]
    assert window.minimumHeight() == MINIMUM_TIMER_SIZE[1]
    assert window.width() == 520
    assert window.height() == 210
    assert window._clock.text() == "01:02:03"
    assert window._footer.text() == "Architecture  ·  #工作 #设计"
    assert window._clock.font().family() == CLOCK_FONT_FAMILIES[sys.platform]
    assert window._clock.font().weight() == QFont.Weight.DemiBold
    assert "TIME LOG" not in [label.text() for label in window.findChildren(type(window._clock))]
    image = window.grab().toImage()
    accent = QColor("#69e36d")
    assert all(
        image.pixelColor(x, y) != accent
        for y in range(window.height() - 24, window.height() - 10)
        for x in range(20, window.width() - 20)
    )
    visible_card_corner = QPoint(
        window.width() - SHADOW_INSET - 1,
        window.height() - SHADOW_INSET - 1,
    )
    assert window._resize_edges(visible_card_corner) == (
        Qt.Edge.RightEdge | Qt.Edge.BottomEdge
    )
    assert window._resize_edges(QPoint(CARD_INSET, CARD_INSET)) == (
        Qt.Edge.LeftEdge | Qt.Edge.TopEdge
    )

    QTest.mouseDClick(window, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert controller.toggle_count == 1
    window.close()
