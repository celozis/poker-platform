from datetime import UTC, datetime, timedelta

from app.blind_clock import BlindClock

START = datetime(2026, 9, 26, 19, 0, tzinfo=UTC)
# Level 1, level 2, a break, level 3.
DURATIONS = (timedelta(minutes=20), timedelta(minutes=20), timedelta(minutes=10), timedelta(minutes=20))


def minutes(value: float) -> timedelta:
    return timedelta(minutes=value)


def test_the_clock_starts_on_the_first_level_with_its_full_time() -> None:
    clock = BlindClock.started(DURATIONS, START)

    assert (clock.item, clock.running, clock.time_left(START)) == (0, True, minutes(20))


def test_the_clock_counts_down() -> None:
    clock = BlindClock.started(DURATIONS, START)

    assert clock.at(START + minutes(5)).time_left(START + minutes(5)) == minutes(15)


def test_the_clock_moves_on_to_the_next_level_and_break_by_itself() -> None:
    clock = BlindClock.started(DURATIONS, START)

    later = START + minutes(20)
    assert (clock.at(later).item, clock.at(later).time_left(later)) == (1, minutes(20))
    later = START + minutes(45)
    assert (clock.at(later).item, clock.at(later).time_left(later)) == (2, minutes(5))
    later = START + minutes(51)
    assert (clock.at(later).item, clock.at(later).time_left(later)) == (3, minutes(19))


def test_the_last_level_goes_on_with_no_time_left() -> None:
    clock = BlindClock.started(DURATIONS, START)

    later = START + minutes(500)
    assert (clock.at(later).item, clock.at(later).time_left(later)) == (3, timedelta(0))


def test_a_pause_stops_the_clock_and_resuming_goes_on_from_there() -> None:
    clock = BlindClock.started(DURATIONS, START).paused(START + minutes(5))

    much_later = START + minutes(60)
    assert not clock.running
    assert (clock.at(much_later).item, clock.time_left(much_later)) == (0, minutes(15))

    resumed = clock.resumed(much_later)
    assert resumed.running
    assert resumed.at(much_later + minutes(16)).item == 1
    assert resumed.at(much_later + minutes(16)).time_left(much_later + minutes(16)) == minutes(19)


def test_a_pause_counts_the_levels_that_have_passed_first() -> None:
    clock = BlindClock.started(DURATIONS, START).paused(START + minutes(25))

    assert (clock.item, clock.time_left(START + minutes(90))) == (1, minutes(15))


def test_switching_level_starts_it_afresh_whether_running_or_paused() -> None:
    running = BlindClock.started(DURATIONS, START)
    at = START + minutes(5)

    forward = running.moved(1, at)
    assert (forward.item, forward.running, forward.time_left(at)) == (1, True, minutes(20))
    to_break = forward.moved(1, at)
    assert (to_break.item, to_break.time_left(at)) == (2, minutes(10))
    back = to_break.moved(-1, at)
    assert (back.item, back.time_left(at)) == (1, minutes(20))

    paused = running.paused(at).moved(1, START + minutes(30))
    assert (paused.item, paused.running, paused.time_left(START + minutes(99))) == (
        1,
        False,
        minutes(20),
    )


def test_there_is_nothing_before_the_first_level_or_after_the_last() -> None:
    clock = BlindClock.started(DURATIONS, START)

    assert not clock.can_move(-1, START)
    assert clock.can_move(1, START)
    last = clock.moved(1, START).moved(1, START).moved(1, START)
    assert not last.can_move(1, START)
