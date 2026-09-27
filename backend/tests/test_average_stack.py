from app.board import average_stack


def test_the_chips_of_every_entry_are_shared_among_the_players_left() -> None:
    # 10 players of 20 000 each, 4 of them left.
    assert average_stack(
        starting_stack=20000, addon_stack=None, entries=10, addons=0, players_left=4
    ) == 50000


def test_a_reentry_brings_another_starting_stack_and_an_addon_its_own_chips() -> None:
    # 10 players and 2 re-entries of 20 000, 5 add-ons of 30 000, 8 players left:
    # (12 × 20 000 + 5 × 30 000) / 8 = 390 000 / 8.
    assert average_stack(
        starting_stack=20000, addon_stack=30000, entries=12, addons=5, players_left=8
    ) == 48750


def test_the_average_is_rounded_to_a_whole_chip() -> None:
    assert average_stack(
        starting_stack=10000, addon_stack=None, entries=2, addons=0, players_left=3
    ) == 6667


def test_there_is_no_average_while_nobody_is_at_a_table() -> None:
    assert average_stack(
        starting_stack=20000, addon_stack=None, entries=0, addons=0, players_left=0
    ) is None
