"""Stable timer view models independent from Qt and HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any


SIZE_PRESETS = {
    "small": (300, 132, 44, 16, 10),
    "medium": (420, 180, 72, 22, 13),
    "large": (560, 236, 104, 28, 16),
}


@dataclass(frozen=True)
class TimerSession:
    session_id: str
    title: str
    accent: str
    state: str
    elapsed_seconds: int
    synchronized_at: float

    @property
    def is_running(self) -> bool:
        return self.state == "active"

    def displayed_seconds(self, now: float | None = None) -> int:
        if not self.is_running:
            return self.elapsed_seconds
        current = monotonic() if now is None else now
        return self.elapsed_seconds + max(0, int(current - self.synchronized_at))


@dataclass(frozen=True)
class TimerState:
    sessions: tuple[TimerSession, ...] = ()
    selected_session_id: str = ""
    status: str = "ready"
    message: str = ""

    @property
    def selected(self) -> TimerSession | None:
        for session in self.sessions:
            if session.session_id == self.selected_session_id:
                return session
        return self.sessions[0] if self.sessions else None


def parse_timer_state(payload: dict[str, Any], selected_session_id: str = "") -> TimerState:
    raw_sessions = payload.get("active_sessions")
    if raw_sessions is None:
        raw_session = payload.get("active_session")
        raw_sessions = [raw_session] if raw_session else []
    sessions = tuple(_parse_session(item) for item in raw_sessions if isinstance(item, dict))
    selected = selected_session_id if any(item.session_id == selected_session_id for item in sessions) else ""
    return TimerState(
        sessions=sessions,
        selected_session_id=selected or (sessions[0].session_id if sessions else ""),
    )


def parse_command_session(payload: dict[str, Any]) -> TimerSession:
    return _parse_session(payload)


def _parse_session(payload: dict[str, Any]) -> TimerSession:
    entry = payload.get("entry")
    if not isinstance(entry, dict):
        raise ValueError("timer session entry is required")
    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("timer session_id is required")
    title = str(entry.get("label") or entry.get("title") or "").strip()
    if not title:
        raise ValueError("timer title is required")
    activity = entry.get("bound_object")
    activity = activity if isinstance(activity, dict) else {}
    accent = str(activity.get("accent") or entry.get("accent") or "#ff5c7a").strip()
    state = str(payload.get("state") or entry.get("status") or "").strip()
    if state not in {"active", "paused"}:
        raise ValueError(f"unsupported timer state: {state}")
    elapsed = max(0, int(payload.get("elapsed_seconds") or 0))
    return TimerSession(
        session_id=session_id,
        title=title,
        accent=accent,
        state=state,
        elapsed_seconds=elapsed,
        synchronized_at=monotonic(),
    )


def format_clock(seconds: int) -> str:
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
