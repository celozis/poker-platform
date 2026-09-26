from datetime import UTC, datetime
from typing import Any

from app.schemas import TournamentIn
from app.tournament_rules import tournament_errors
from tests.tournaments import a_break, a_level, a_tournament

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def errors(**overrides: Any) -> list[str]:
    return tournament_errors(TournamentIn.model_validate(a_tournament(**overrides)), NOW)


def test_a_valid_tournament_has_no_errors() -> None:
    assert errors() == []


def test_addon_level_must_be_within_the_structure() -> None:
    # The default structure has three levels and a break; breaks are not numbered.
    assert errors(addon_at_level=3) == []
    assert errors(addon_at_level=4) == ["Add-on: уровня 4 нет в структуре, в ней уровни с 1 по 3"]


def test_reentry_and_late_registration_levels_must_be_within_the_structure() -> None:
    assert errors(reentry_until_level=0) == [
        "Re-entry: уровня 0 нет в структуре, в ней уровни с 1 по 3"
    ]
    assert errors(late_registration_until_level=7) == [
        "Поздняя регистрация: уровня 7 нет в структуре, в ней уровни с 1 по 3"
    ]


def test_options_that_are_not_offered_need_no_level() -> None:
    assert errors(reentry_until_level=None, addon_at_level=None, late_registration_until_level=None) == []


def test_structure_needs_at_least_one_level() -> None:
    no_levels = ["В структуре блайндов нет ни одного уровня"]
    assert errors(structure=[]) == no_levels
    assert errors(structure=[a_break()]) == no_levels


def test_each_level_and_break_must_make_sense() -> None:
    structure = [
        a_level(0, 200),
        a_level(300, 200),
        a_level(100, 200, ante=-25),
        a_break(minutes=0),
        a_level(100, 200, minutes=0),
    ]

    assert errors(
        structure=structure,
        reentry_until_level=None,
        addon_at_level=None,
        late_registration_until_level=None,
    ) == [
        "Уровень 1: малый блайнд должен быть больше нуля",
        "Уровень 2: большой блайнд не может быть меньше малого",
        "Уровень 3: анте не может быть отрицательным",
        "Перерыв после уровня 3: длительность должна быть больше нуля",
        "Уровень 4: длительность должна быть больше нуля",
    ]


def test_tournament_needs_a_name_a_future_start_a_buy_in_and_chips() -> None:
    assert errors(
        name="   ",
        starts_at="2026-09-26T11:59:00Z",
        buy_in=-1,
        starting_stack=0,
    ) == [
        "Укажите название турнира",
        "Время начала уже прошло",
        "Бай-ин не может быть отрицательным",
        "Стартовый стек должен быть больше нуля",
    ]


def test_a_free_tournament_is_allowed() -> None:
    assert errors(buy_in=0) == []


def test_name_and_amounts_must_fit_in_the_database() -> None:
    assert errors(name="Т" * 201, buy_in=3_000_000_000, starting_stack=3_000_000_000) == [
        "Название длиннее 200 символов",
        "Бай-ин слишком большой",
        "Стартовый стек слишком большой",
    ]


def test_a_break_before_the_first_level_is_named_so() -> None:
    assert errors(structure=[a_break(minutes=0), *a_tournament()["structure"]]) == [
        "Перерыв в начале: длительность должна быть больше нуля"
    ]
