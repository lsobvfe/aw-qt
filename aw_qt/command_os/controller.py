"""Timer application controller."""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import uuid4

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .client import CommandClient
from .models import (
    TimerState,
    parse_command_session,
    parse_leisure_state,
    parse_tag_catalog,
    parse_timer_state,
)

logger = logging.getLogger(__name__)


class TimerController(QObject):
    state_changed = pyqtSignal(object)
    authorization_required = pyqtSignal()

    def __init__(self, client: CommandClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client = client
        self._state = TimerState(status="loading")
        self._pending: dict[str, str] = {}
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15_000)
        self._refresh_timer.timeout.connect(self.refresh)
        self._display_timer = QTimer(self)
        self._display_timer.setInterval(1_000)
        self._display_timer.timeout.connect(self._publish)
        client.completed.connect(self._on_completed)
        client.failed.connect(self._on_failed)

    @property
    def state(self) -> TimerState:
        return self._state

    def start(self) -> None:
        self._refresh_timer.start()
        self._display_timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        if "refresh" in self._pending.values():
            return
        self._track(self._client.execute("sp.time_log.desktop.snapshot", {}), "refresh")

    def toggle(self) -> None:
        session = self._state.selected
        if session is None:
            return
        command = "sp.time_log.timer.pause" if session.is_running else "sp.time_log.timer.resume"
        self._track(self._client.execute(command, {"session_id": session.session_id}), "session")

    def finish(self) -> None:
        session = self._state.selected
        if session is None:
            return
        self._track(
            self._client.execute(
                "sp.time_log.timer.finish",
                {
                    "session_id": session.session_id,
                    "completion": "desktop-widget",
                    "idempotency_key": f"desktop-finish:{session.session_id}",
                },
            ),
            "finish",
        )

    def start_leisure(self) -> None:
        leisure = self._state.leisure
        if leisure is None or not leisure.available or leisure.session is not None:
            return
        self._track(
            self._client.execute(
                "sp.time_log.leisure.start",
                {"idempotency_key": f"desktop-leisure-start:{uuid4().hex}"},
            ),
            "desktop",
        )

    def stop_leisure(self) -> None:
        leisure = self._state.leisure
        if leisure is None or leisure.session is None:
            return
        self._track(
            self._client.execute(
                "sp.time_log.leisure.stop",
                {
                    "session_id": leisure.session.session_id,
                    "idempotency_key": (
                        f"desktop-leisure-stop:{leisure.session.session_id}"
                    ),
                },
            ),
            "desktop",
        )

    def toggle_leisure(self) -> None:
        leisure = self._state.leisure
        if leisure is None or leisure.session is None:
            return
        if leisure.session.is_running:
            self.pause_leisure()
        else:
            self.resume_leisure()

    def pause_leisure(self) -> None:
        self._set_leisure_state("pause")

    def resume_leisure(self) -> None:
        self._set_leisure_state("resume")

    def _set_leisure_state(self, action: str) -> None:
        leisure = self._state.leisure
        if leisure is None or leisure.session is None:
            return
        session_id = leisure.session.session_id
        self._track(
            self._client.execute(
                f"sp.time_log.leisure.{action}",
                {
                    "session_id": session_id,
                    "idempotency_key": (
                        f"desktop-leisure-{action}:{session_id}:{uuid4().hex}"
                    ),
                },
            ),
            "leisure",
        )

    def update_leisure_settings(self, payload: dict) -> None:
        self._track(
            self._client.execute(
                "sp.time_log.leisure.settings.update",
                {
                    **payload,
                    "idempotency_key": (
                        f"desktop-leisure-settings:{uuid4().hex}"
                    ),
                },
            ),
            "leisure",
        )

    def start_activity(self, activity_id: str) -> None:
        activity = next(
            (item for item in self._state.activities if item.activity_id == activity_id),
            None,
        )
        if activity is None:
            return
        self._track(
            self._client.execute(
                "sp.time_log.timer.start",
                {
                    "activity": activity.command_payload(),
                    "mode": "countup",
                    "tags": list(activity.tags),
                    "idempotency_key": f"desktop-start:{uuid4().hex}",
                },
            ),
            "start",
        )

    def change_activity(self, activity_id: str) -> None:
        session = self._state.selected
        activity = next(
            (item for item in self._state.activities if item.activity_id == activity_id),
            None,
        )
        if session is None or activity is None:
            return
        self._track(
            self._client.execute(
                "sp.time_log.timer.metadata.update",
                {
                    "session_id": session.session_id,
                    "activity_id": activity.activity_id,
                    "activity": activity.command_payload(),
                },
            ),
            "session",
        )

    def update_tags(self, tags: list[str]) -> None:
        session = self._state.selected
        if session is None:
            return
        self._track(
            self._client.execute(
                "sp.time_log.timer.metadata.update",
                {"session_id": session.session_id, "tags": tags},
            ),
            "session",
        )

    def create_tag(self, name: str) -> None:
        value = name.strip()
        if value:
            self._track(
                self._client.execute("sp.time_log.tags.create", {"name": value}),
                "tags",
            )

    def delete_tag(self, name: str) -> None:
        value = name.strip()
        if value:
            self._track(
                self._client.execute("sp.time_log.tags.delete", {"name": value}),
                "tags",
            )

    def select(self, session_id: str) -> None:
        if any(item.session_id == session_id for item in self._state.sessions):
            self._state = replace(
                self._state,
                selected_session_id=session_id,
            )
            self._publish()

    def report_error(self, message: str) -> None:
        self._state = replace(
            self._state,
            status="error",
            message=message,
        )
        self._publish()

    def _track(self, request_id: str, operation: str) -> None:
        self._pending[request_id] = operation

    def _on_completed(self, request_id: str, payload: dict) -> None:
        operation = self._pending.pop(request_id, "")
        try:
            if operation in {"refresh", "desktop"}:
                self._state = parse_timer_state(payload, self._state.selected_session_id)
                logger.info("Time Log desktop state refreshed with %d sessions", len(self._state.sessions))
            elif operation == "session":
                updated = parse_command_session(payload)
                sessions = tuple(updated if item.session_id == updated.session_id else item for item in self._state.sessions)
                self._state = replace(
                    self._state,
                    sessions=sessions,
                    selected_session_id=updated.session_id,
                    status="ready",
                    message="",
                )
            elif operation == "start":
                started = parse_command_session(payload)
                sessions = (started, *tuple(item for item in self._state.sessions if item.session_id != started.session_id))
                self._state = replace(
                    self._state,
                    sessions=sessions,
                    selected_session_id=started.session_id,
                    status="ready",
                    message="",
                )
            elif operation == "tags":
                raw_tags = payload.get("tags")
                if not isinstance(raw_tags, list):
                    raise ValueError("tag mutation tags must be a list")
                self._state = replace(
                    self._state,
                    tags=parse_tag_catalog(raw_tags),
                    status="ready",
                    message="",
                )
            elif operation == "leisure":
                self._state = replace(
                    self._state,
                    leisure=parse_leisure_state(payload),
                    status="ready",
                    message="",
                )
            elif operation == "finish":
                self.refresh()
                return
        except (TypeError, ValueError) as exc:
            logger.exception("Time Log desktop state parsing failed")
            self._state = replace(
                self._state,
                status="error",
                message=str(exc),
            )
        self._publish()

    def _on_failed(self, request_id: str, message: str) -> None:
        logger.warning("Time Log desktop request failed: %s", message)
        self._pending.pop(request_id, None)
        if message == "Desktop authorization is required":
            self.authorization_required.emit()
        self._state = replace(
            self._state,
            status="error",
            message=message,
        )
        self._publish()

    def _publish(self) -> None:
        self.state_changed.emit(self._state)
        leisure = self._state.leisure
        if (
            leisure is not None
            and leisure.session is not None
            and leisure.session.is_running
            and leisure.session.displayed_seconds() == 0
            and "refresh" not in self._pending.values()
        ):
            self.refresh()
