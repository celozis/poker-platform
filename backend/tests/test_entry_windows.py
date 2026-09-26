import pytest

from app.entry_windows import EntryWindows, entry_windows, level_reached
from app.schemas import BlindLevel, Break, StructureItem


def level(small_blind: int) -> BlindLevel:
    return BlindLevel(
        kind="level", small_blind=small_blind, big_blind=2 * small_blind, ante=0, duration_minutes=20
    )


PAUSE = Break(kind="break", duration_minutes=10)
# Items: 0 level 1, 1 level 2, 2 break, 3 level 3, 4 level 4.
STRUCTURE: list[StructureItem] = [level(100), level(200), PAUSE, level(300), level(400)]


@pytest.mark.parametrize(("item", "level_number"), [(0, 1), (1, 2), (2, 2), (3, 3), (4, 4)])
def test_a_break_belongs_to_the_level_before_it(item: int, level_number: int) -> None:
    assert level_reached(STRUCTURE, item) == level_number


def test_a_break_at_the_very_start_comes_before_level_one() -> None:
    assert level_reached([PAUSE, level(100)], 0) == 0


def windows(item: int, reentry: int | None = None, addon: int | None = None, late: int | None = None) -> EntryWindows:
    return entry_windows(
        STRUCTURE,
        item,
        reentry_until_level=reentry,
        addon_at_level=addon,
        late_registration_until_level=late,
    )


@pytest.mark.parametrize(("item", "open_"), [(0, True), (1, True), (2, True), (3, False), (4, False)])
def test_reentry_and_late_registration_are_open_up_to_their_level_and_its_break(
    item: int, open_: bool
) -> None:
    assert windows(item, reentry=2, late=2) == EntryWindows(
        reentry=open_, addon=False, late_registration=open_
    )


@pytest.mark.parametrize(("item", "open_"), [(0, False), (1, True), (2, True), (3, False)])
def test_addon_is_open_only_on_its_level_and_the_break_after_it(item: int, open_: bool) -> None:
    assert windows(item, addon=2).addon is open_


def test_options_the_tournament_does_not_offer_are_never_open() -> None:
    assert windows(0) == EntryWindows(reentry=False, addon=False, late_registration=False)
