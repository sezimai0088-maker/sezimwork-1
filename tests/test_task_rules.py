from datetime import date

from bot.task_rules import (
    AlertKind,
    BlockReason,
    TaskStatus,
    alert_to_send,
    due_options,
    needs_comment,
    next_streaks,
    normalize_text,
    parse_task_lines,
)

TODAY = date(2026, 10, 29)  # четверг


def test_parse_lines_strips_numbers_and_bullets():
    text = "1. Сдать отчёт\n2) Позвонить поставщику\n- Проверить склад\n• Купить краску\n\n   "
    assert parse_task_lines(text) == ["Сдать отчёт", "Позвонить поставщику", "Проверить склад", "Купить краску"]


def test_parse_lines_removes_duplicates_and_short():
    assert parse_task_lines("Сдать отчёт\nсдать  отчет!\nа\n") == ["Сдать отчёт"]


def test_parse_lines_keeps_numbers_inside_text():
    assert parse_task_lines("Заказать 10 мешков цемента") == ["Заказать 10 мешков цемента"]


def test_normalize_ignores_case_yo_and_punctuation():
    assert normalize_text("Сдать ОТЧЁТ!!") == normalize_text("сдать   отчет")


def test_streak_not_done_grows_and_done_resets():
    assert next_streaks(TaskStatus.NOT_DONE, None, TODAY, 0, 0) == (1, 0)
    assert next_streaks(TaskStatus.NOT_DONE, None, TODAY, 1, 0) == (2, 0)
    assert next_streaks(TaskStatus.DONE, None, TODAY, 2, 0) == (0, 0)


def test_continue_on_time_is_not_counted_but_overdue_is():
    assert next_streaks(TaskStatus.CONTINUE, date(2026, 10, 30), TODAY, 1, 0) == (0, 0)
    assert next_streaks(TaskStatus.CONTINUE, date(2026, 10, 28), TODAY, 1, 0) == (2, 0)


def test_blocked_has_separate_counter():
    assert next_streaks(TaskStatus.BLOCKED, None, TODAY, 1, 0) == (1, 1)
    assert next_streaks(TaskStatus.BLOCKED, None, TODAY, 1, 1) == (1, 2)


def test_alert_fires_once_on_threshold():
    assert alert_to_send((1, 0), (2, 0), 2) == AlertKind.NOT_DONE
    assert alert_to_send((2, 0), (3, 0), 2) is None  # уже отправляли
    assert alert_to_send((0, 0), (1, 0), 2) is None
    assert alert_to_send((0, 1), (0, 2), 2) == AlertKind.BLOCKED


def test_two_days_not_done_scenario():
    streaks = (0, 0)
    alerts = []
    for _ in range(3):
        new = next_streaks(TaskStatus.NOT_DONE, None, TODAY, *streaks)
        alerts.append(alert_to_send(streaks, new, 2))
        streaks = new
    assert alerts == [None, AlertKind.NOT_DONE, None]


def test_comment_required_rules():
    assert needs_comment(TaskStatus.CANCELLED, None)
    assert needs_comment(TaskStatus.BLOCKED, BlockReason.OTHER)
    assert not needs_comment(TaskStatus.BLOCKED, BlockReason.WEATHER)
    assert not needs_comment(TaskStatus.DONE, None)


def test_due_options_midweek_and_friday():
    opts = due_options(TODAY)  # четверг
    assert opts["tomorrow"] == date(2026, 10, 30)
    assert "week" not in opts  # пятница = завтра, отдельная кнопка не нужна
    opts = due_options(date(2026, 10, 26))  # понедельник
    assert opts["week"] == date(2026, 10, 30)
