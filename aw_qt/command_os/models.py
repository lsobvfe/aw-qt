"""Stable desktop Time Log view models independent from Qt and HTTP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
class LeisureFixedWindow:
    window_id: str
    start_minute: int
    end_minute: int


@dataclass(frozen=True)
class LeisureSelector:
    selector_id: str
    kind: str
    value: str


@dataclass(frozen=True)
class LeisurePolicy:
    enabled: bool
    timezone: str
    earn_threshold_minutes: int
    reward_minutes: int
    fixed_windows: tuple[LeisureFixedWindow, ...]
    selectors: tuple[LeisureSelector, ...]
    revision: int

    def command_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "timezone": self.timezone,
            "earn_threshold_minutes": self.earn_threshold_minutes,
            "reward_minutes": self.reward_minutes,
            "fixed_windows": [
                {
                    "window_id": item.window_id,
                    "start_minute": item.start_minute,
                    "end_minute": item.end_minute,
                }
                for item in self.fixed_windows
            ],
            "selectors": [
                {
                    "selector_id": item.selector_id,
                    "kind": item.kind,
                    "value": item.value,
                }
                for item in self.selectors
            ],
        }


@dataclass(frozen=True)
class LeisureSession:
    session_id: str
    source: str
    display_source: str
    ends_at: datetime
    remaining_seconds: int
    progress_basis_seconds: int
    consumed_seconds: int
    synchronized_at: float

    def displayed_seconds(self, now: float | None = None) -> int:
        current = monotonic() if now is None else now
        return max(
            0,
            self.remaining_seconds
            - _whole_elapsed_seconds(current - self.synchronized_at),
        )

    def progress(self, now: float | None = None) -> float:
        remaining = self.displayed_seconds(now)
        return max(
            0.0,
            min(1.0, 1.0 - remaining / max(1, self.progress_basis_seconds)),
        )


@dataclass(frozen=True)
class LeisureState:
    available: bool
    policy: LeisurePolicy | None
    balance_seconds: int
    progress_seconds: int
    threshold_seconds: int | None
    session: LeisureSession | None
    unavailable_reason: str


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
            elapsed += _whole_elapsed_seconds(current - self.synchronized_at)
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
    leisure: LeisureState | None = None
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
    raw_leisure = payload.get("leisure")
    if not isinstance(raw_sessions, list):
        raise ValueError("desktop snapshot active_sessions must be a list")
    if not isinstance(raw_activities, list):
        raise ValueError("desktop snapshot activities must be a list")
    if not isinstance(raw_tags, list):
        raise ValueError("desktop snapshot tag_catalog must be a list")
    if not isinstance(raw_leisure, dict):
        raise ValueError("desktop snapshot leisure must be an object")
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
        leisure=parse_leisure_state(raw_leisure),
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


def parse_leisure_state(payload: dict[str, Any]) -> LeisureState:
    account = _object(payload.get("account"), "leisure account")
    raw_policy = payload.get("policy")
    policy = (
        _parse_leisure_policy(_object(raw_policy, "leisure policy"))
        if raw_policy is not None
        else None
    )
    raw_session = payload.get("session")
    session = (
        _parse_leisure_session(_object(raw_session, "leisure session"))
        if raw_session is not None
        else None
    )
    return LeisureState(
        available=_boolean(payload, "available"),
        policy=policy,
        balance_seconds=_integer(account, "balance_seconds", minimum=0),
        progress_seconds=_integer(account, "progress_seconds", minimum=0),
        threshold_seconds=_optional_integer(
            account,
            "threshold_seconds",
            minimum=60,
        ),
        session=session,
        unavailable_reason=_string(payload, "unavailable_reason"),
    )


def _parse_leisure_policy(payload: dict[str, Any]) -> LeisurePolicy:
    raw_windows = payload.get("fixed_windows")
    raw_selectors = payload.get("selectors")
    if not isinstance(raw_windows, list):
        raise ValueError("leisure fixed_windows must be a list")
    if not isinstance(raw_selectors, list):
        raise ValueError("leisure selectors must be a list")
    windows = tuple(
        LeisureFixedWindow(
            window_id=_string(item, "window_id", required=True),
            start_minute=_integer(item, "start_minute", minimum=0),
            end_minute=_integer(item, "end_minute", minimum=0),
        )
        for item in (_object(value, "leisure fixed window") for value in raw_windows)
    )
    selectors = tuple(
        LeisureSelector(
            selector_id=_string(item, "selector_id", required=True),
            kind=_choice(item, "kind", {"activity", "tag"}),
            value=_string(item, "value", required=True),
        )
        for item in (_object(value, "leisure selector") for value in raw_selectors)
    )
    return LeisurePolicy(
        enabled=_boolean(payload, "enabled"),
        timezone=_string(payload, "timezone", required=True),
        earn_threshold_minutes=_integer(
            payload,
            "earn_threshold_minutes",
            minimum=1,
        ),
        reward_minutes=_integer(payload, "reward_minutes", minimum=1),
        fixed_windows=windows,
        selectors=selectors,
        revision=_integer(payload, "revision", minimum=1),
    )


def _parse_leisure_session(payload: dict[str, Any]) -> LeisureSession:
    if not _boolean(payload, "active"):
        raise ValueError("desktop leisure session must be active")
    return LeisureSession(
        session_id=_string(payload, "session_id", required=True),
        source=_choice(payload, "source", {"fixed", "earned"}),
        display_source=_choice(
            payload,
            "display_source",
            {"fixed", "earned"},
        ),
        ends_at=_datetime(payload, "ends_at"),
        remaining_seconds=_integer(payload, "remaining_seconds", minimum=0),
        progress_basis_seconds=_integer(
            payload,
            "progress_basis_seconds",
            minimum=1,
        ),
        consumed_seconds=_integer(payload, "consumed_seconds", minimum=0),
        synchronized_at=monotonic(),
    )


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


def _choice(
    payload: dict[str, Any],
    field: str,
    choices: set[str],
) -> str:
    value = _string(payload, field, required=True)
    if value not in choices:
        raise ValueError(f"{field} must be one of {sorted(choices)}")
    return value


def _datetime(payload: dict[str, Any], field: str) -> datetime:
    value = _string(payload, field, required=True)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime") from exc


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


def _optional_integer(
    payload: dict[str, Any],
    field: str,
    *,
    minimum: int | None = None,
) -> int | None:
    if payload.get(field) is None:
        return None
    return _integer(payload, field, minimum=minimum)


def format_clock(seconds: int) -> str:
    value = max(0, int(seconds))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _whole_elapsed_seconds(value: float) -> int:
    return max(0, int(max(0.0, value) + 1e-6))
