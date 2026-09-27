import pytest

from app.points import points


def test_the_winner_of_a_36_player_tournament_gets_50_points() -> None:
    assert points(place=1, players=36) == 50


def test_the_last_place_gets_nothing_however_big_the_field() -> None:
    assert [points(place=n, players=n) for n in (2, 9, 36, 120)] == [0, 0, 0, 0]


def test_points_of_every_place_of_a_nine_player_tournament() -> None:
    assert [points(place, players=9) for place in range(1, 10)] == [20, 11, 7, 5, 3, 2, 1, 1, 0]


def test_a_small_field_gives_few_points() -> None:
    assert [points(place, players=2) for place in (1, 2)] == [4, 0]
    assert [points(place, players=3) for place in (1, 2, 3)] == [7, 2, 0]


def test_a_higher_place_never_gets_fewer_points() -> None:
    for players in range(2, 101):
        by_place = [points(place, players) for place in range(1, players + 1)]
        assert by_place == sorted(by_place, reverse=True), players


def test_a_place_outside_the_field_has_no_points() -> None:
    for place, players in ((0, 5), (6, 5), (1, 0)):
        with pytest.raises(ValueError):
            points(place, players)
