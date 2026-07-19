from dataclasses import replace

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


def test_start_defers_initial_refresh_until_event_loop_is_running() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    client = FakeClient()
    controller = TimerController(client)

    controller.start()
    assert client.requests == []

    app.processEvents()
    assert client.requests == [("sp.time_log.desktop.snapshot", {})]
    assert controller._pending == {"request-1": "refresh"}
    controller._refresh_timer.stop()
    controller._display_timer.stop()


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
            "leisure": {
                "available": False,
                "policy": None,
                "account": {
                    "balance_seconds": 0,
                    "progress_seconds": 0,
                    "threshold_seconds": None,
                },
                "session": None,
                "unavailable_reason": "not_configured",
                "synchronized_at": "2026-07-19T00:00:00+00:00",
            },
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


def test_desktop_controller_starts_stops_and_updates_leisure() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    client = FakeClient()
    controller = TimerController(client)
    controller._state = parse_timer_state(
        {
            "active_sessions": [],
            "activities": [],
            "tag_catalog": [],
            "leisure": {
                "available": True,
                "policy": None,
                "account": {
                    "balance_seconds": 300,
                    "progress_seconds": 0,
                    "threshold_seconds": 1500,
                },
                "session": None,
                "unavailable_reason": "",
                "synchronized_at": "2026-07-19T00:00:00+00:00",
            },
        }
    )

    controller.start_leisure()
    controller.update_leisure_settings(
        {
            "enabled": True,
            "timezone": "Asia/Shanghai",
            "earn_threshold_minutes": 40,
            "reward_minutes": 7,
            "fixed_windows": [],
            "selectors": [],
        }
    )
    assert client.requests[0][0] == "sp.time_log.leisure.start"
    assert client.requests[1][0] == "sp.time_log.leisure.settings.update"
    assert client.requests[1][1]["earn_threshold_minutes"] == 40

    active = parse_timer_state(
        {
            "active_sessions": [],
            "activities": [],
            "tag_catalog": [],
            "leisure": {
                "available": True,
                "policy": None,
                "account": {
                    "balance_seconds": 300,
                    "progress_seconds": 0,
                    "threshold_seconds": 1500,
                },
                "session": {
                    "session_id": "leisure-1",
                    "state": "active",
                    "source": "earned",
                    "display_source": "earned",
                    "started_at": "2026-07-19T00:00:00+00:00",
                    "fixed_starts_at": None,
                    "ends_at": "2026-07-19T00:05:00+00:00",
                    "remaining_seconds": 300,
                    "consumed_seconds": 0,
                },
                "unavailable_reason": "",
                "synchronized_at": "2026-07-19T00:00:00+00:00",
            },
        }
    )
    controller._state = active
    controller.toggle_leisure()
    assert client.requests[2][0] == "sp.time_log.leisure.pause"
    assert client.requests[2][1]["session_id"] == "leisure-1"

    assert active.leisure is not None
    assert active.leisure.session is not None
    controller._state = replace(
        active,
        leisure=replace(
            active.leisure,
            session=replace(active.leisure.session, state="paused"),
        ),
    )
    controller.toggle_leisure()
    controller.stop_leisure()
    assert client.requests[3][0] == "sp.time_log.leisure.resume"
    assert client.requests[4][0] == "sp.time_log.leisure.stop"
