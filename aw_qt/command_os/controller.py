"""Timer application controller."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .client import CommandClient
from .models import TimerState, parse_command_session, parse_timer_state

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
        self.refresh()

    def refresh(self) -> None:
        if "refresh" in self._pending.values():
            return
        self._track(self._client.execute("sp.time_log.open", {"view": "launcher"}), "refresh")

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

    def select(self, session_id: str) -> None:
        if any(item.session_id == session_id for item in self._state.sessions):
            self._state = TimerState(
                sessions=self._state.sessions,
                selected_session_id=session_id,
                status=self._state.status,
                message=self._state.message,
            )
            self._publish()

    def report_error(self, message: str) -> None:
        self._state = TimerState(
            sessions=self._state.sessions,
            selected_session_id=self._state.selected_session_id,
            status="error",
            message=message,
        )
        self._publish()

    def _track(self, request_id: str, operation: str) -> None:
        self._pending[request_id] = operation

    def _on_completed(self, request_id: str, payload: dict) -> None:
        operation = self._pending.pop(request_id, "")
        try:
            if operation == "refresh":
                self._state = parse_timer_state(payload, self._state.selected_session_id)
                logger.info("Time Log desktop state refreshed with %d sessions", len(self._state.sessions))
            elif operation == "session":
                updated = parse_command_session(payload)
                sessions = tuple(updated if item.session_id == updated.session_id else item for item in self._state.sessions)
                self._state = TimerState(sessions=sessions, selected_session_id=updated.session_id)
            elif operation == "finish":
                self.refresh()
                return
        except (TypeError, ValueError) as exc:
            logger.exception("Time Log desktop state parsing failed")
            self._state = TimerState(
                sessions=self._state.sessions,
                selected_session_id=self._state.selected_session_id,
                status="error",
                message=str(exc),
            )
        self._publish()

    def _on_failed(self, request_id: str, message: str) -> None:
        logger.warning("Time Log desktop request failed: %s", message)
        self._pending.pop(request_id, None)
        if message == "Desktop authorization is required":
            self.authorization_required.emit()
        self._state = TimerState(
            sessions=self._state.sessions,
            selected_session_id=self._state.selected_session_id,
            status="error",
            message=message,
        )
        self._publish()

    def _publish(self) -> None:
        self.state_changed.emit(self._state)
