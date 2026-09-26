from collections import Counter
from random import Random

import pytest

from app.seating import (
    Move,
    Seat,
    final_table_seating,
    initial_seating,
    seat_for_newcomer,
    suggested_move,
)


def table_sizes(seating: dict[int, Seat]) -> dict[int, int]:
    return dict(Counter(seat.table for seat in seating.values()))


@pytest.mark.parametrize(
    ("players", "seats_per_table", "expected_sizes"),
    [
        (2, 9, [2]),
        (9, 9, [9]),
        (10, 9, [5, 5]),
        (19, 9, [7, 6, 6]),
        (25, 6, [5, 5, 5, 5, 5]),
        (13, 6, [5, 4, 4]),
    ],
)
def test_start_seats_everyone_at_as_few_tables_as_possible_evenly(
    players: int, seats_per_table: int, expected_sizes: list[int]
) -> None:
    seating = initial_seating(list(range(1, players + 1)), seats_per_table, Random(1))

    assert sorted(seating) == list(range(1, players + 1))
    assert sorted(table_sizes(seating).values(), reverse=True) == expected_sizes
    assert set(table_sizes(seating)) == set(range(1, len(expected_sizes) + 1))


def test_no_two_players_share_a_seat_and_seats_exist_at_the_table() -> None:
    seating = initial_seating(list(range(1, 20)), 9, Random(2))

    assert len(set(seating.values())) == 19
    assert all(1 <= seat.seat <= 9 for seat in seating.values())


def test_the_draw_is_random() -> None:
    players = list(range(1, 19))

    assert initial_seating(players, 9, Random(1)) != initial_seating(players, 9, Random(2))


def test_a_newcomer_sits_at_the_table_with_the_fewest_players() -> None:
    seating = {1: Seat(1, 1), 2: Seat(1, 2), 3: Seat(1, 3), 4: Seat(2, 4), 5: Seat(2, 9)}

    seat = seat_for_newcomer(seating, 9, Random(1))

    assert seat.table == 2
    assert seat.seat not in {4, 9}
    assert 1 <= seat.seat <= 9


def test_among_equally_small_tables_the_newcomer_takes_the_first() -> None:
    seating = {1: Seat(1, 1), 2: Seat(2, 1), 3: Seat(3, 1)}

    assert seat_for_newcomer(seating, 9, Random(1)).table == 1


def test_when_every_table_is_full_the_newcomer_opens_a_new_one() -> None:
    seating = {1: Seat(1, 1), 2: Seat(1, 2), 3: Seat(2, 1), 4: Seat(2, 2)}

    assert seat_for_newcomer(seating, 2, Random(1)).table == 3


def at_table(table: int, *seats: int, first_player: int) -> dict[int, Seat]:
    return {first_player + i: Seat(table, seat) for i, seat in enumerate(seats)}


def test_even_tables_need_no_move() -> None:
    seating = at_table(1, 1, 2, 3, first_player=1) | at_table(2, 5, 6, first_player=10)

    assert suggested_move(seating, 9) is None


def test_a_table_two_players_short_gets_one_from_the_biggest_table() -> None:
    # 7 and 5: after the move 6 and 6.
    seating = at_table(1, 1, 2, 3, 4, 5, 6, 7, first_player=1) | at_table(
        2, 2, 4, 5, 6, 7, first_player=10
    )

    move = suggested_move(seating, 9)

    assert move == Move(player_id=1, from_seat=Seat(1, 1), to_seat=Seat(2, 1))


def test_the_biggest_table_gives_a_player_to_the_smallest_one() -> None:
    seating = (
        at_table(1, 1, 2, 3, 4, 5, 6, first_player=1)
        | at_table(2, 1, 2, 3, 4, 5, 6, 7, first_player=10)
        | at_table(3, 3, 4, 5, 6, 7, first_player=20)
    )

    # 18 players at 7-seat tables still need all three tables.
    move = suggested_move(seating, 7)

    assert move is not None
    assert (move.from_seat.table, move.to_seat) == (2, Seat(3, 1))


def test_a_table_no_longer_needed_is_broken_up_one_player_at_a_time() -> None:
    # 12 players fit at two 9-seat tables, so the smallest of the three tables goes.
    seating = (
        at_table(1, 1, 2, 3, 4, 5, first_player=1)
        | at_table(2, 1, 2, 3, 4, first_player=10)
        | at_table(3, 1, 2, 3, first_player=20)
    )

    move = suggested_move(seating, 9)

    assert move == Move(player_id=20, from_seat=Seat(3, 1), to_seat=Seat(2, 5))


def test_following_the_suggestions_ends_with_even_tables() -> None:
    seating = (
        at_table(1, 1, 2, 3, 4, 5, 6, 7, 8, 9, first_player=1)
        | at_table(2, 1, 2, first_player=10)
        | at_table(3, 1, 2, 3, 4, 5, 6, 7, 8, first_player=20)
    )
    moves = 0
    while (move := suggested_move(seating, 9)) is not None:
        assert seating[move.player_id] == move.from_seat
        assert move.to_seat not in seating.values()
        seating[move.player_id] = move.to_seat
        moves += 1
        assert moves < 20

    assert sorted(table_sizes(seating).values()) == [6, 6, 7]


def test_players_that_fit_at_one_table_are_left_to_the_final_table() -> None:
    seating = at_table(1, 1, 2, 3, 4, first_player=1) | at_table(2, 1, first_player=10)

    assert suggested_move(seating, 9) is None


def test_players_that_fit_at_one_table_are_drawn_again_for_the_final_table() -> None:
    seating = at_table(1, 2, 5, 7, 9, first_player=1) | at_table(3, 1, 4, 8, 9, first_player=10)

    final = final_table_seating(seating, 9, Random(1))

    assert final is not None
    assert sorted(final) == sorted(seating)
    assert {seat.table for seat in final.values()} == {1}
    assert len(set(final.values())) == 8
    assert final != final_table_seating(seating, 9, Random(2))


@pytest.mark.parametrize(
    "seating",
    [
        at_table(1, 1, 2, 3, 4, 5, first_player=1) | at_table(2, 1, 2, 3, 4, 5, first_player=10),
        at_table(2, 1, 2, 3, first_player=1),
    ],
    ids=["more players than one table seats", "one table already"],
)
def test_there_is_no_final_table_yet(seating: dict[int, Seat]) -> None:
    assert final_table_seating(seating, 9, Random(1)) is None
