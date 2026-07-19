from aw_qt.command_os.ui.theme import ThemeManager, leisure_card_color


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


def test_leisure_color_uses_fixed_thirty_minute_scale() -> None:
    green = leisure_card_color(30 * 60)
    five_minutes = leisure_card_color(5 * 60)
    red = leisure_card_color(0)

    assert green == "#3fc77a"
    assert red == "#e85d5d"
    assert five_minutes not in {green, red}
