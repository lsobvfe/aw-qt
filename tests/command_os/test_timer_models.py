import pytest

from aw_qt.command_os.models import (
    format_clock,
    parse_command_session,
    parse_timer_state,
)


def test_timer_snapshot_projects_running_and_paused_sessions() -> None:
    state = parse_timer_state(
        {
            "active_sessions": [
                {
                    "session_id": "timer-active",
                    "state": "active",
                    "elapsed_seconds": 125,
                    "entry": {
                        "label": "Deep Work",
                        "bound_object": {"label": "Architecture"},
                        "tags": ["工作", "设计"],
                        "accent": "#69e36d",
                        "emoji": "◆",
                        "timer_mode": "countup",
                        "countdown_minutes": 25,
                        "pomodoro_work_minutes": 25,
                        "pomodoro_rest_minutes": 5,
                    },
                },
                {
                    "session_id": "timer-paused",
                    "state": "paused",
                    "elapsed_seconds": 3605,
                    "entry": {
                        "title": "Reading",
                        "label": "Reading",
                        "bound_object": {"label": ""},
                        "tags": ["阅读"],
                        "accent": "#ffe14d",
                        "emoji": "◇",
                        "timer_mode": "countup",
                        "countdown_minutes": 25,
                        "pomodoro_work_minutes": 25,
                        "pomodoro_rest_minutes": 5,
                    },
                },
            ],
            "activities": [
                {
                    "id": "activity-deep-work",
                    "title": "Deep Work",
                    "label": "Deep Work",
                    "bound_object": {
                        "module": "smart_planner",
                        "type": "activity",
                        "id": "",
                        "label": "Architecture",
                    },
                    "tags": ["工作", "设计"],
                    "accent": "#69e36d",
                    "emoji": "◆",
                    "default_seconds": 1500,
                    "source": "base",
                    "source_group": "basic",
                    "source_badge": "Built-in",
                    "confirmed": True,
                    "description": "Architecture focus",
                    "hidden": False,
                    "pinned": False,
                    "priority": 5,
                    "template_id": "template-deep-work",
                    "conflict": False,
                }
            ],
            "tag_catalog": [
                {"name": "工作", "is_default": True},
                {"name": "设计", "is_default": False},
            ],
            "leisure": {
                "available": True,
                "policy": {
                    "enabled": True,
                    "timezone": "Asia/Shanghai",
                    "earn_threshold_minutes": 25,
                    "reward_minutes": 5,
                    "fixed_windows": [],
                    "selectors": [],
                    "revision": 1,
                },
                "account": {
                    "balance_seconds": 600,
                    "progress_seconds": 0,
                    "threshold_seconds": 1500,
                },
                "session": {
                    "session_id": "leisure-1",
                    "active": True,
                    "source": "earned",
                    "display_source": "earned",
                    "started_at": "2026-07-19T00:00:00+00:00",
                    "fixed_starts_at": None,
                    "ends_at": "2026-07-19T00:10:00+00:00",
                    "remaining_seconds": 600,
                    "progress_basis_seconds": 600,
                    "consumed_seconds": 0,
                },
                "unavailable_reason": "",
                "synchronized_at": "2026-07-19T00:00:00+00:00",
            },
        },
        selected_session_id="timer-paused",
    )

    assert state.selected_session_id == "timer-paused"
    assert state.selected is not None
    assert state.selected.title == "Reading"
    assert state.selected.displayed_seconds(
        now=state.selected.synchronized_at + 30
    ) == 3605
    assert state.sessions[0].displayed_seconds(
        now=state.sessions[0].synchronized_at + 30
    ) == 155
    assert format_clock(state.selected.elapsed_seconds) == "01:00:05"
    assert state.sessions[0].footer_text == "Deep Work  ·  #工作 #设计"
    assert state.activities[0].command_payload()["bound_object"]["label"] == "Architecture"
    assert state.activities[0].command_payload()["template_id"] == "template-deep-work"
    assert state.activities[0].command_payload()["priority"] == 5
    assert [tag.name for tag in state.tags] == ["工作", "设计"]
    assert state.leisure is not None
    assert state.leisure.session is not None
    assert state.leisure.session.displayed_seconds(
        state.leisure.session.synchronized_at + 30
    ) == 570
    assert state.leisure.session.progress(
        state.leisure.session.synchronized_at + 300
    ) == 0.5


def test_timer_snapshot_uses_backend_mode_configuration_for_clock_value() -> None:
    countdown = parse_command_session(
        {
            "session_id": "countdown",
            "state": "active",
            "elapsed_seconds": 125,
            "entry": {
                "label": "Countdown",
                "bound_object": {"label": ""},
                "tags": [],
                "accent": "#ffe14d",
                "emoji": "◇",
                "timer_mode": "countdown",
                "countdown_minutes": 5,
                "pomodoro_work_minutes": 25,
                "pomodoro_rest_minutes": 5,
            },
        }
    )
    pomodoro = parse_command_session(
        {
            "session_id": "pomodoro",
            "state": "paused",
            "elapsed_seconds": 130,
            "entry": {
                "label": "Pomodoro",
                "bound_object": {"label": ""},
                "tags": [],
                "accent": "#ffe14d",
                "emoji": "◇",
                "timer_mode": "pomodoro",
                "countdown_minutes": 25,
                "pomodoro_work_minutes": 2,
                "pomodoro_rest_minutes": 1,
            },
        }
    )

    assert countdown.displayed_seconds(
        now=countdown.synchronized_at + 5
    ) == 170
    assert pomodoro.displayed_seconds() == 50


def test_timer_snapshot_rejects_incomplete_protocol_data() -> None:
    with pytest.raises(ValueError, match="session_id"):
        parse_command_session(
            {
                "state": "active",
                "elapsed_seconds": 1,
                "entry": {
                    "title": "Missing session",
                    "bound_object": {},
                    "tags": [],
                    "accent": "#ffe14d",
                },
            }
        )


def test_desktop_snapshot_rejects_parallel_legacy_session_shape() -> None:
    with pytest.raises(ValueError, match="active_sessions"):
        parse_timer_state(
            {
                "active_session": {},
                "activities": [],
                "tag_catalog": [],
                "leisure": {},
            }
        )
