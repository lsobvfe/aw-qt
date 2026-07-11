from PyQt6.QtCore import QObject, QCoreApplication, pyqtSignal

from aw_qt.command_os.controller import TimerController
from aw_qt.command_os.models import parse_timer_state


class FakeClient(QObject):
    completed = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.request_count = 0
        self.requests: list[tuple[str, dict]] = []

    def execute(self, command: str, args: dict) -> str:
        self.request_count += 1
        self.requests.append((command, args))
        return f"request-{self.request_count}"


def test_failed_refresh_clears_pending_request() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    client = FakeClient()
    controller = TimerController(client)

    controller.refresh()
    client.failed.emit("request-1", "Desktop authorization is required")
    app.processEvents()
    controller.refresh()

    assert controller._pending == {"request-2": "refresh"}


def test_desktop_controller_uses_shared_event_and_tag_commands() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    client = FakeClient()
    controller = TimerController(client)
    controller._state = parse_timer_state(
        {
            "active_sessions": [
                {
                    "session_id": "session-1",
                    "state": "active",
                    "elapsed_seconds": 5,
                    "entry": {
                        "title": "Current",
                        "label": "Current",
                        "bound_object": {"label": "Current"},
                        "tags": ["工作"],
                        "accent": "#ffe14d",
                        "emoji": "◇",
                        "timer_mode": "countup",
                        "countdown_minutes": 25,
                        "pomodoro_work_minutes": 25,
                        "pomodoro_rest_minutes": 5,
                    },
                }
            ],
            "activities": [
                {
                    "id": "activity-2",
                    "title": "Design",
                    "label": "Design",
                    "bound_object": {
                        "module": "smart_planner",
                        "type": "activity",
                        "id": "",
                        "label": "Design",
                    },
                    "tags": ["设计"],
                    "accent": "#69e36d",
                    "emoji": "◆",
                    "default_seconds": 1500,
                    "source": "base",
                    "source_group": "basic",
                    "source_badge": "Built-in",
                    "confirmed": True,
                    "description": "",
                    "hidden": False,
                    "pinned": False,
                    "priority": 0,
                    "template_id": "",
                    "conflict": False,
                }
            ],
            "tag_catalog": [
                {"name": "工作", "is_default": True},
                {"name": "设计", "is_default": False},
            ],
        }
    )

    controller.start_activity("activity-2")
    controller.change_activity("activity-2")
    controller.update_tags(["工作", "设计"])
    controller.create_tag("口语")
    controller.delete_tag("设计")
    app.processEvents()

    commands = [command for command, _args in client.requests]
    assert commands == [
        "sp.time_log.timer.start",
        "sp.time_log.timer.metadata.update",
        "sp.time_log.timer.metadata.update",
        "sp.time_log.tags.create",
        "sp.time_log.tags.delete",
    ]
    assert client.requests[1][1]["session_id"] == "session-1"
    assert client.requests[2][1]["tags"] == ["工作", "设计"]
