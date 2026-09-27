"""Rating points for a place in a tournament: the league's default formula.

points = 10 × (√(players ÷ place) − 1), rounded to the nearest whole point (a half up).

The winner of a bigger field gets more (4 of 2 players, 20 of 9, 50 of 36), the points fall off
fast down the places, and the last place always gets 0. `players` counts everyone who played,
once each however many times they re-entered: places run from 1 to that number.

The formula is league-wide; in the MVP there is just this one, as blind templates live in code
(ADR-0004). Points are stored with each result, so a later formula does not rewrite old seasons."""

from math import floor, sqrt


def points(place: int, players: int) -> int:
    if not 1 <= place <= players:
        raise ValueError(f"place {place} is not among {players} players")
    return floor(10 * (sqrt(players / place) - 1) + 0.5)
