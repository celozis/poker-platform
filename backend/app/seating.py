"""Where players sit: the draw at the start, seats for newcomers, moves that keep tables even,
and the final table. Pure functions over a seating (player id → seat), no database.

Tables are numbered from 1 and seats from 1 to the tournament's seats per table."""

from dataclasses import dataclass
from math import ceil
from random import Random

Seating = dict[int, "Seat"]


@dataclass(frozen=True, order=True)
class Seat:
    table: int
    seat: int


def initial_seating(player_ids: list[int], seats_per_table: int, rng: Random) -> Seating:
    """The draw at the start: as few tables as fit everyone, player counts differing by at most one,
    random tables and seats."""
    table_count = ceil(len(player_ids) / seats_per_table)
    shuffled = rng.sample(player_ids, len(player_ids))
    seating: Seating = {}
    for table in range(1, table_count + 1):
        # Dealing round the tables keeps them within one player of each other.
        at_table = shuffled[table - 1 :: table_count]
        seats = rng.sample(range(1, seats_per_table + 1), len(at_table))
        seating.update({player: Seat(table, seat) for player, seat in zip(at_table, seats)})
    return seating


def _occupied(seating: Seating) -> dict[int, set[int]]:
    """Taken seats by table, for the tables that have anyone at them."""
    tables: dict[int, set[int]] = {}
    for seat in seating.values():
        tables.setdefault(seat.table, set()).add(seat.seat)
    return tables


def _free_seats(taken: set[int], seats_per_table: int) -> list[int]:
    return [seat for seat in range(1, seats_per_table + 1) if seat not in taken]


def seat_for_newcomer(seating: Seating, seats_per_table: int, rng: Random) -> Seat:
    """A random free seat at the table with the fewest players (the first of equals) for a late
    registration or a re-entry; a new table when every table is full."""
    tables = _occupied(seating)
    open_tables = [t for t, taken in sorted(tables.items()) if len(taken) < seats_per_table]
    if not open_tables:
        return Seat(max(tables, default=0) + 1, rng.randint(1, seats_per_table))
    table = min(open_tables, key=lambda t: len(tables[t]))
    return Seat(table, rng.choice(_free_seats(tables[table], seats_per_table)))


@dataclass(frozen=True)
class Move:
    player_id: int
    from_seat: Seat
    to_seat: Seat


def suggested_move(seating: Seating, seats_per_table: int) -> Move | None:
    """The next move that keeps tables even, or None when they are even already.

    A table that is no longer needed is broken up first, one player at a time; otherwise a player
    moves from the biggest table to one with two players fewer. The suggestion is the same every
    time for the same seating, so the admin can be shown it and then apply it. Players who fit at
    one table are left alone: they go to the final table (final_table_seating)."""
    tables = _occupied(seating)
    if len(tables) <= 1 or len(seating) <= seats_per_table:
        return None
    by_size = sorted(tables, key=lambda t: (len(tables[t]), t))
    if len(tables) > ceil(len(seating) / seats_per_table):
        # The smallest table goes; of equals, the one with the highest number.
        smallest = min(len(taken) for taken in tables.values())
        source = max(t for t in tables if len(tables[t]) == smallest)
        target = min((t for t in tables if t != source), key=lambda t: (len(tables[t]), t))
    else:
        target = by_size[0]
        source = max(tables, key=lambda t: (len(tables[t]), -t))
        if len(tables[source]) - len(tables[target]) <= 1:
            return None
    from_seat = Seat(source, min(tables[source]))
    player_id = next(player for player, seat in seating.items() if seat == from_seat)
    return Move(player_id, from_seat, Seat(target, _free_seats(tables[target], seats_per_table)[0]))


def final_table_seating(seating: Seating, seats_per_table: int, rng: Random) -> Seating | None:
    """Once the players left fit at one table, everyone is drawn again for the final table
    (table 1). None while more tables are needed, or when there is one table already."""
    if len(_occupied(seating)) <= 1 or len(seating) > seats_per_table:
        return None
    return initial_seating(list(seating), seats_per_table, rng)
