from aw_qt.command_os.ui.theme import ThemeManager


def test_explicit_theme_mode_notifies_even_when_resolved_color_is_unchanged() -> None:
    theme = ThemeManager()
    emitted: list[str] = []
    theme.changed.connect(emitted.append)
    explicit_mode = theme.resolved

    theme.set_mode("system")
    theme.set_mode(explicit_mode)

    assert theme.mode == explicit_mode
    assert emitted[-1] == explicit_mode
    theme.set_mode("system")
