from typing import Any

# Relative to FakeClock's 2026-09-26 12:00 UTC: a week ahead.
NEXT_WEEK = "2026-10-03T19:00:00+07:00"


def a_level(small_blind: int, big_blind: int, ante: int = 0, minutes: int = 20) -> dict[str, Any]:
    return {
        "kind": "level",
        "small_blind": small_blind,
        "big_blind": big_blind,
        "ante": ante,
        "duration_minutes": minutes,
    }


def a_break(minutes: int = 10) -> dict[str, Any]:
    return {"kind": "break", "duration_minutes": minutes}


def a_tournament(**overrides: Any) -> dict[str, Any]:
    """A valid tournament as the admin panel sends it; override any field."""
    return {
        "name": "Пятничный турнир",
        "starts_at": NEXT_WEEK,
        "buy_in": 2000,
        "starting_stack": 20000,
        "structure": [a_level(100, 200), a_level(200, 400), a_break(), a_level(300, 600, ante=75)],
        "reentry_until_level": 2,
        "addon_at_level": 2,
        "late_registration_until_level": 3,
    } | overrides
