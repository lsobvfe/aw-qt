from PyQt6.QtCore import Qt

from aw_qt.command_os.models import parse_timer_state
from aw_qt.command_os.ui.leisure_dialog import LeisureSettingsDialog


def test_leisure_settings_dialog_builds_configurable_server_payload() -> None:
    state = parse_timer_state(
        {
            "active_sessions": [],
            "activities": [
                {
                    "id": "base:focus-work",
                    "title": "Deep Work",
                    "label": "专注工作",
                    "bound_object": {
                        "module": "smart_planner",
                        "type": "activity",
                        "id": "",
                        "label": "Focus",
                    },
                    "tags": ["工作"],
                    "accent": "#35C77A",
                    "emoji": "◎",
                    "default_seconds": 1500,
                    "source": "base",
                    "source_group": "basic",
                    "source_badge": "Built-in",
                    "confirmed": True,
                    "description": "",
                    "hidden": False,
                    "pinned": False,
                    "priority": 5,
                    "template_id": "",
                    "conflict": False,
                },
                {
                    "id": "system:2026-07-19:10",
                    "title": "Suggestion",
                    "label": "临时建议",
                    "bound_object": {
                        "module": "smart_planner",
                        "type": "activity",
                        "id": "",
                        "label": "Suggestion",
                    },
                    "tags": ["工作"],
                    "accent": "#35C77A",
                    "emoji": "◇",
                    "default_seconds": 1500,
                    "source": "system",
                    "source_group": "system",
                    "source_badge": "Suggested",
                    "confirmed": False,
                    "description": "",
                    "hidden": False,
                    "pinned": False,
                    "priority": 0,
                    "template_id": "",
                    "conflict": False,
                },
            ],
            "tag_catalog": [{"name": "工作", "is_default": True}],
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
    dialog = LeisureSettingsDialog(
        None,
        state.activities,
        state.tags,
    )
    dialog._timezone.setCurrentText("Asia/Shanghai")
    dialog._threshold.setValue(40)
    dialog._reward.setValue(7)
    dialog._add_window(12 * 60, 14 * 60, "lunch")
    dialog._activities.item(0).setCheckState(Qt.CheckState.Checked)
    dialog._tags.item(0).setCheckState(Qt.CheckState.Checked)

    payload = dialog.policy_payload()

    assert payload["earn_threshold_minutes"] == 40
    assert payload["reward_minutes"] == 7
    assert payload["fixed_windows"] == [
        {
            "window_id": "lunch",
            "start_minute": 12 * 60,
            "end_minute": 14 * 60,
        }
    ]
    assert {item["kind"] for item in payload["selectors"]} == {
        "activity",
        "tag",
    }
    assert len(dialog._stable_activities) == 1
    dialog.close()
