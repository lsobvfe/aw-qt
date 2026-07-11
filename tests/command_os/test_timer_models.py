import pytest

from aw_qt.command_os.models import (
    SIZE_PRESETS,
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
                        "bound_object": {"accent": "#69e36d"},
                    },
                },
                {
                    "session_id": "timer-paused",
                    "state": "paused",
                    "elapsed_seconds": 3605,
                    "entry": {"title": "Reading"},
                },
            ]
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


def test_timer_snapshot_rejects_incomplete_protocol_data() -> None:
    with pytest.raises(ValueError, match="session_id"):
        parse_command_session(
            {
                "state": "active",
                "elapsed_seconds": 1,
                "entry": {"title": "Missing session"},
            }
        )


def test_timer_widget_size_presets_scale_clock_as_primary_content() -> None:
    small = SIZE_PRESETS["small"]
    medium = SIZE_PRESETS["medium"]
    large = SIZE_PRESETS["large"]

    assert small[:2] == (300, 132)
    assert small[2] < medium[2] < large[2]
    assert medium[2] >= 72
    assert large[2] >= 104
