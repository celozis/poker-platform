from datetime import UTC, date, datetime, timedelta, timezone

from app.seasons import Season, season_at

NOVOSIBIRSK = timezone(timedelta(hours=7))


def test_a_season_is_a_half_of_the_year() -> None:
    assert season_at(datetime(2026, 9, 26, 12, 0, tzinfo=UTC)) == Season(
        id="2026-2",
        name="2-е полугодие 2026",
        starts_at=datetime(2026, 7, 1, tzinfo=NOVOSIBIRSK),
        ends_at=datetime(2027, 1, 1, tzinfo=NOVOSIBIRSK),
    )


def test_the_first_half_of_the_year_is_a_season_of_its_own() -> None:
    season = season_at(datetime(2027, 3, 8, 19, 0, tzinfo=NOVOSIBIRSK))

    assert season.name == "1-е полугодие 2027"
    assert (season.first_day, season.last_day) == (date(2027, 1, 1), date(2027, 6, 30))


def test_seasons_change_at_midnight_in_the_league_time_not_in_utc() -> None:
    # 23:30 on 30 June in Novosibirsk is still the first half; 00:30 on 1 July is the second,
    # though in UTC both are on 30 June.
    last_evening = datetime(2027, 6, 30, 23, 30, tzinfo=NOVOSIBIRSK)
    after_midnight = datetime(2027, 7, 1, 0, 30, tzinfo=NOVOSIBIRSK)

    assert season_at(last_evening).name == "1-е полугодие 2027"
    assert season_at(after_midnight).name == "2-е полугодие 2027"
    assert after_midnight.astimezone(UTC).date() == date(2027, 6, 30)


def test_new_year_starts_a_new_season() -> None:
    assert season_at(datetime(2026, 12, 31, 23, 59, tzinfo=NOVOSIBIRSK)).name == "2-е полугодие 2026"
    assert season_at(datetime(2027, 1, 1, 0, 0, tzinfo=NOVOSIBIRSK)).name == "1-е полугодие 2027"
