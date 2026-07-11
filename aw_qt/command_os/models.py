"""Stable desktop Time Log view models independent from Qt and HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class ActivityCandidate:
    activity_id: str
    title: str
    label: str
    bound_object: dict[str, str]
    tags: tuple[str, ...]
    source: str
    source_group: str
    source_badge: str
    default_seconds: int
    confirmed: bool
    accent: str
    emoji: str
    description: str
    hidden: bool
    pinned: bool
    priority: int
    template_id: str
    conflict: bool

    def command_payload(self) -> dict[str, Any]:
        return {
            "id": self.activity_id,
            "title": self.title,
            "label": self.label,
            "bound_object": dict(self.bound_object),
            "tags": list(self.tags),
            "source": self.source,
            "source_group": self.source_group,
            "source_badge": self.source_badge,
            "default_seconds": self.default_seconds,
            "confirmed": self.confirmed,
            "accent": self.accent,
            "emoji": self.emoji,
            "description": self.description,
            "hidden": self.hidden,
            "pinned": self.pinned,
            "priority": self.priority,
            "template_id": self.template_id,
            "conflict": self.conflict,
        }


@dataclass(frozen=True)
class TagOption:
    name: str
    is_default: bool


@dataclass(frozen=True)
class TimerSession:
    session_id: str
    title: str
    bound_object_label: str
    tags: tuple[str, ...]
    accent: str
    emoji: str
    timer_mode: str
    countdown_minutes: int
    pomodoro_work_minutes: int
    pomodoro_rest_minutes: int
    state: str
    elapsed_seconds: int
    synchronized_at: float

    @property
    def is_running(self) -> bool:
        return self.state == "active"

    def displayed_seconds(self, now: float | None = None) -> int:
        elapsed = self.elapsed_seconds
        if self.is_running:
            current = monotonic() if now is None else now
            elapsed += max(0, int(current - self.synchronized_at))
        if self.timer_mode == "countdown":
            return max(0, self.countdown_minutes * 60 - elapsed)
        if self.timer_mode == "pomodoro":
            work_seconds = self.pomodoro_work_minutes * 60
            rest_seconds = self.pomodoro_rest_minutes * 60
            offset = elapsed % (work_seconds + rest_seconds)
            if offset < work_seconds:
                return work_seconds - offset
            return rest_seconds - (offset - work_seconds)
        return elapsed

    @property
    def footer_text(self) -> str:
        tag_text = " ".join(f"#{tag}" for tag in self.tags)
        return "  ·  ".join(part for part in (self.title, tag_text) if part)


@dataclass(frozen=True)
class TimerState:
    sessions: tuple[TimerSession, ...] = ()
    activities: tuple[ActivityCandidate, ...] = ()
    tags: tuple[TagOption, ...] = ()
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
    raw_activities = payload.get("activities")
    raw_tags = payload.get("tag_catalog")
    if not isinstance(raw_sessions, list):
        raise ValueError("desktop snapshot active_sessions must be a list")
    if not isinstance(raw_activities, list):
        raise ValueError("desktop snapshot activities must be a list")
    if not isinstance(raw_tags, list):
        raise ValueError("desktop snapshot tag_catalog must be a list")
    sessions = tuple(_parse_session(_object(item, "timer session")) for item in raw_sessions)
    activities = tuple(
        _parse_activity(_object(item, "activity candidate"))
        for item in raw_activities
    )
    tags = parse_tag_catalog(raw_tags)
    selected = selected_session_id if any(item.session_id == selected_session_id for item in sessions) else ""
    return TimerState(
        sessions=sessions,
        activities=activities,
        tags=tags,
        selected_session_id=selected or (sessions[0].session_id if sessions else ""),
    )


def parse_command_session(payload: dict[str, Any]) -> TimerSession:
    return _parse_session(payload)


def parse_tag_catalog(payload: list[Any]) -> tuple[TagOption, ...]:
    tags: list[TagOption] = []
    for item in payload:
        tag = _object(item, "tag catalog item")
        tags.append(
            TagOption(
                name=_string(tag, "name", required=True),
                is_default=_boolean(tag, "is_default"),
            )
        )
    return tuple(tags)


def _parse_session(payload: dict[str, Any]) -> TimerSession:
    entry = _object(payload.get("entry"), "timer session entry")
    session_id = _string(payload, "session_id", required=True)
    title = _string(entry, "label", required=True)
    activity = _object(entry.get("bound_object"), "timer bound_object")
    tags = entry.get("tags")
    if not isinstance(tags, list):
        raise ValueError("timer tags must be a list")
    if not all(isinstance(tag, str) for tag in tags):
        raise ValueError("timer tags must contain strings")
    state = _string(payload, "state", required=True)
    if state not in {"active", "paused"}:
        raise ValueError(f"unsupported timer state: {state}")
    timer_mode = _string(entry, "timer_mode", required=True)
    if timer_mode not in {"countup", "countdown", "pomodoro"}:
        raise ValueError(f"unsupported timer mode: {timer_mode}")
    elapsed = _integer(payload, "elapsed_seconds", minimum=0)
    return TimerSession(
        session_id=session_id,
        title=title,
        bound_object_label=_string(activity, "label"),
        tags=tuple(tag.strip() for tag in tags if tag.strip()),
        accent=_string(entry, "accent", required=True),
        emoji=_string(entry, "emoji", required=True),
        timer_mode=timer_mode,
        countdown_minutes=_integer(entry, "countdown_minutes", minimum=1),
        pomodoro_work_minutes=_integer(
            entry, "pomodoro_work_minutes", minimum=1
        ),
        pomodoro_rest_minutes=_integer(
            entry, "pomodoro_rest_minutes", minimum=1
        ),
        state=state,
        elapsed_seconds=elapsed,
        synchronized_at=monotonic(),
    )


def _parse_activity(payload: dict[str, Any]) -> ActivityCandidate:
    activity_id = _string(payload, "id", required=True)
    title = _string(payload, "title", required=True)
    label = _string(payload, "label", required=True)
    bound_object = _object(payload.get("bound_object"), "activity bound_object")
    tags = payload.get("tags")
    if not isinstance(tags, list):
        raise ValueError("activity tags must be a list")
    if not all(isinstance(tag, str) for tag in tags):
        raise ValueError("activity tags must contain strings")
    source_group = _string(payload, "source_group", required=True)
    if source_group not in {
        "today",
        "recent",
        "pinned",
        "context",
        "schedule",
        "system",
        "basic",
    }:
        raise ValueError(f"unsupported activity source_group: {source_group}")
    return ActivityCandidate(
        activity_id=activity_id,
        title=title,
        label=label,
        bound_object={
            key: _string(bound_object, key)
            for key in ("module", "type", "id", "label")
        },
        tags=tuple(tag.strip() for tag in tags if tag.strip()),
        source=_string(payload, "source", required=True),
        source_group=source_group,
        source_badge=_string(payload, "source_badge", required=True),
        default_seconds=_integer(payload, "default_seconds", minimum=60),
        confirmed=_boolean(payload, "confirmed"),
        accent=_string(payload, "accent", required=True),
        emoji=_string(payload, "emoji", required=True),
        description=_string(payload, "description"),
        hidden=_boolean(payload, "hidden"),
        pinned=_boolean(payload, "pinned"),
        priority=_integer(payload, "priority"),
        template_id=_string(payload, "template_id"),
        conflict=_boolean(payload, "conflict"),
    )


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _string(payload: dict[str, Any], field: str, *, required: bool = False) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    result = value.strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    return result


def _boolean(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _integer(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
) -> int:
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


def format_clock(seconds: int) -> str:
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
