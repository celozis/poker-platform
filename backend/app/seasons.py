"""Rating seasons: the club rating starts again every half of the year.

A season runs from 1 January to 30 June or from 1 July to 31 December, from midnight to midnight
in the league's time. Clubs have no time zone yet; the league's clubs are in Novosibirsk and
Krasnoyarsk, which keep UTC+7 all year round. A tournament belongs to the season its scheduled
start falls in, however late it finishes (ADR-0008).

Seasons are league-wide and, like blind templates, live in code in the MVP."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

LEAGUE_TIME = timezone(timedelta(hours=7))


def league_time_text(moment: datetime) -> str:
    """"03.10.2026 19:00": in the league's time, as the clubs' clocks show it."""
    return moment.astimezone(LEAGUE_TIME).strftime("%d.%m.%Y %H:%M")


@dataclass(frozen=True)
class Season:
    # The year and its half, such as "2026-2".
    id: str
    name: str
    starts_at: datetime
    # The moment the next season starts: a tournament starting then is no longer in this one.
    ends_at: datetime

    @property
    def first_day(self) -> date:
        return self.starts_at.date()

    @property
    def last_day(self) -> date:
        return (self.ends_at - timedelta(days=1)).date()


def season_at(moment: datetime) -> Season:
    local = moment.astimezone(LEAGUE_TIME)
    if local.month <= 6:
        return Season(
            id=f"{local.year}-1",
            name=f"1-е полугодие {local.year}",
            starts_at=datetime(local.year, 1, 1, tzinfo=LEAGUE_TIME),
            ends_at=datetime(local.year, 7, 1, tzinfo=LEAGUE_TIME),
        )
    return Season(
        id=f"{local.year}-2",
        name=f"2-е полугодие {local.year}",
        starts_at=datetime(local.year, 7, 1, tzinfo=LEAGUE_TIME),
        ends_at=datetime(local.year + 1, 1, 1, tzinfo=LEAGUE_TIME),
    )


def season_by_id(season_id: str) -> Season | None:
    """The season with this id ("2026-2"), or None when there is no such season. Only this
    century's: far-off years would overflow the dates of the season before or after."""
    match = re.fullmatch(r"(20\d\d)-([12])", season_id)
    if match is None:
        return None
    year, half = int(match[1]), int(match[2])
    return season_at(datetime(year, 1 if half == 1 else 7, 1, tzinfo=LEAGUE_TIME))


def previous_season(season: Season) -> Season:
    return season_at(season.starts_at - timedelta(days=1))


def next_season(season: Season) -> Season:
    return season_at(season.ends_at)
