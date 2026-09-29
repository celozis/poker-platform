"""The Telegram bot: a player links their Telegram to their player by phone and sees the
tournaments of their club. Updates go through the bot's real dispatcher into the test database;
Telegram itself is replaced by tests/bot.py, and the admin API shows what the bot has done."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.bot import BotChat, agree, go_through_the_bot
from tests.clock import FakeClock
from tests.factories import create_club
from tests.game import CASH, knock_out, played_tournament, ready_tournament
from tests.players import a_player, switch_to_another_club
from tests.tournaments import a_tournament


@pytest.fixture
def chat(clock: FakeClock) -> BotChat:
    return BotChat(clock)


def test_start_greets_the_player_and_asks_for_consent(chat: BotChat) -> None:
    reply = chat.send("/start")

    assert "Сибирской лиги покера" in reply
    assert "согласие на обработку персональных данных" in reply
    assert chat.buttons() == ["Согласен", "Не согласен"]


def test_after_consent_the_bot_asks_for_the_phone(chat: BotChat) -> None:
    chat.send("/start")

    reply = chat.press("Согласен")

    assert "поделитесь номером телефона" in reply
    assert chat.asks_for_contact()


def test_without_consent_the_bot_goes_no_further(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    chat.send("/start")

    assert "Без согласия" in chat.press("Не согласен")
    assert not chat.asks_for_contact()

    # Neither a command nor a shared phone gets past the consent.
    chat.send("/schedule")
    assert chat.buttons() == ["Согласен", "Не согласен"]
    chat.share_contact("+79135551234")
    assert chat.buttons() == ["Согласен", "Не согласен"]
    added = client.post(f"/api/clubs/{club.id}/players", json=a_player(phone="+79135551234"))
    assert added.json()["outcome"] == "created"


def test_a_shared_phone_finds_the_player_the_club_added(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    client.post(f"/api/clubs/{club.id}/players", json=a_player(name="Иван Петров"))
    agree(chat)

    # Telegram sends the number without "+", and the name in Telegram is not the club's.
    reply = chat.share_contact("79135551234", first_name="Ваня", last_name=None)

    assert "Нашли вашу карточку игрока: Иван Петров" in reply
    assert chat.contact_button_removed()


def test_a_phone_new_to_the_league_makes_a_player_named_as_in_telegram(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    agree(chat)

    reply = chat.share_contact("+79135551234", first_name="Мария", last_name="Иванова")

    assert "Мария Иванова" in reply
    # The league knows the phone now: the club's admin gets the same player, not a new one.
    added = client.post(
        f"/api/clubs/{club.id}/players", json=a_player(name="Маша", phone="+79135551234")
    ).json()
    assert added["outcome"] == "added_to_club"
    assert added["player"]["name"] == "Мария Иванова"


def test_the_player_chooses_their_club_and_joins_its_player_list(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    create_club(name="Покер-клуб «Енисей»")
    agree(chat)

    chat.share_contact("+79135551234", first_name="Мария", last_name="Иванова")
    assert chat.buttons() == ["Покер-клуб «Енисей»", "Покер-клуб «Обь»"]
    reply = chat.press("Покер-клуб «Обь»")

    assert "Ваш клуб: Покер-клуб «Обь»" in reply
    club_players = client.get(f"/api/clubs/{club.id}/players").json()
    assert [player["name"] for player in club_players] == ["Мария Иванова"]


def test_a_second_start_knows_the_player_and_makes_no_duplicate(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    go_through_the_bot(chat)

    reply = chat.send("/start")
    assert "Мария Иванова" in reply
    assert "Покер-клуб «Обь»" in reply
    assert chat.buttons() == []
    assert not chat.asks_for_contact()

    chat.share_contact("+79135551234", first_name="Мария", last_name="Иванова")
    club_players = client.get(f"/api/clubs/{club.id}/players").json()
    assert [player["name"] for player in club_players] == ["Мария Иванова"]


def test_schedule_shows_the_clubs_coming_tournaments_with_date_time_and_buy_in(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    tournaments = f"/api/clubs/{club.id}/tournaments"
    client.post(
        tournaments,
        json=a_tournament(
            name="Воскресный турнир", starts_at="2026-10-04T15:00:00+07:00", buy_in=1500
        ),
    )
    client.post(
        tournaments,
        json=a_tournament(
            name="Пятничный турнир", starts_at="2026-10-02T19:30:00+07:00", buy_in=2000
        ),
    )
    go_through_the_bot(chat)

    reply = chat.send("/schedule")

    assert reply == (
        "Покер-клуб «Обь», ближайшие турниры:\n"
        "пт 2 октября, 19:30 — Пятничный турнир, бай-ин 2 000 ₽\n"
        "вс 4 октября, 15:00 — Воскресный турнир, бай-ин 1 500 ₽"
    )


def test_schedule_leaves_out_started_and_cancelled_tournaments_and_other_clubs(
    chat: BotChat, client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    tournaments = f"/api/clubs/{club.id}/tournaments"
    client.post(tournaments, json=a_tournament(name="Субботний турнир"))
    cancelled = client.post(tournaments, json=a_tournament(name="Отменённый турнир")).json()
    client.post(f"{tournaments}/{cancelled['id']}/cancel")
    started, _ = ready_tournament(
        client, club, arrived=2, name="Идущий турнир", late_registration_until_level=None
    )
    client.post(f"{started}/start")
    other_club = switch_to_another_club(client, caplog)
    client.post(
        f"/api/clubs/{other_club.id}/tournaments", json=a_tournament(name="Турнир Енисея")
    )
    go_through_the_bot(chat)

    reply = chat.send("/schedule")

    assert reply == (
        "Покер-клуб «Обь», ближайшие турниры:\n"
        "сб 3 октября, 19:00 — Субботний турнир, бай-ин 2 000 ₽"
    )


def test_schedule_shows_the_ten_soonest_tournaments(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    for day in range(1, 13):
        client.post(
            f"/api/clubs/{club.id}/tournaments",
            json=a_tournament(name=f"Турнир {day}", starts_at=f"2026-10-{day:02}T19:00:00+07:00"),
        )
    go_through_the_bot(chat)

    lines = chat.send("/schedule").splitlines()

    assert len(lines) == 11
    assert lines[1].endswith("Турнир 1, бай-ин 2 000 ₽")
    assert lines[10].endswith("Турнир 10, бай-ин 2 000 ₽")


def test_schedule_says_when_the_club_has_no_coming_tournaments(
    chat: BotChat, club: Club
) -> None:
    go_through_the_bot(chat)

    reply = chat.send("/schedule")

    assert reply == "У клуба Покер-клуб «Обь» пока нет запланированных турниров."


def test_a_tournament_not_started_on_time_stays_in_the_schedule_until_check_in_closes(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    # An hour after the clock's now, 2026-09-26 12:00 UTC.
    client.post(
        f"/api/clubs/{club.id}/tournaments",
        json=a_tournament(name="Вечерний турнир", starts_at="2026-09-26T20:00:00+07:00"),
    )
    go_through_the_bot(chat)

    clock.advance(timedelta(hours=3))
    assert "сб 26 сентября, 20:00 — Вечерний турнир" in chat.send("/schedule")

    # 12 hours after its start the club can no longer check anyone in.
    clock.advance(timedelta(hours=10, minutes=1))
    assert "пока нет запланированных турниров" in chat.send("/schedule")


def test_the_player_can_change_their_club(chat: BotChat, club: Club) -> None:
    create_club(name="Покер-клуб «Енисей»")
    go_through_the_bot(chat)

    chat.send("/club")
    assert chat.buttons() == ["Покер-клуб «Енисей»", "Покер-клуб «Обь»"]
    chat.press("Покер-клуб «Енисей»")

    assert "Покер-клуб «Енисей»" in chat.send("/schedule")


def test_a_new_telegram_account_with_the_players_phone_takes_the_player_over(
    chat: BotChat, clock: FakeClock, club: Club
) -> None:
    go_through_the_bot(chat)
    new_account = BotChat(clock, telegram_id=5002, first_name="Мария", last_name="Иванова")
    agree(new_account)

    reply = new_account.share_contact("+79135551234")

    assert "Нашли вашу карточку игрока: Мария Иванова" in reply
    chat.send("/start")
    assert chat.asks_for_contact()


def test_a_player_linked_again_by_a_new_phone_is_on_their_clubs_list(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    go_through_the_bot(chat)

    # The account's number has changed, and the player shares it again.
    chat.share_contact("+79137770000", first_name="Мария", last_name="Петрова")

    club_players = client.get(f"/api/clubs/{club.id}/players").json()
    assert [player["name"] for player in club_players] == ["Мария Иванова", "Мария Петрова"]


def registered_names(client: TestClient, tournament_url: str) -> list[str]:
    """Who the admin panel shows as registered for the tournament."""
    registrations = client.get(f"{tournament_url}/registrations").json()["registrations"]
    return [registration["player"]["name"] for registration in registrations]


def test_a_player_signs_up_from_the_schedule_and_the_admin_sees_them_registered(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир")
    ).json()
    go_through_the_bot(chat)
    chat.send("/schedule")

    reply = chat.press("Записаться: 3.10 Субботний турнир")

    assert "Вы записаны на турнир «Субботний турнир», сб 3 октября, 19:00" in reply
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    assert registered_names(client, url) == ["Мария Иванова"]


def signed_up(chat: BotChat, client: TestClient, club: Club, **tournament: object) -> str:
    """A tournament of the club («Субботний турнир» on 3 October unless told otherwise) the
    player has gone through the bot and signed up for; returns its admin API URL."""
    created = client.post(
        f"/api/clubs/{club.id}/tournaments",
        json=a_tournament(**({"name": "Субботний турнир"} | tournament)),
    ).json()
    go_through_the_bot(chat)
    chat.send("/schedule")
    chat.press(f"Записаться: 3.10 {created['name']}")
    return f"/api/clubs/{club.id}/tournaments/{created['id']}"


def test_after_signing_up_the_schedule_marks_the_tournament_and_offers_to_drop_out(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    signed_up(chat, client, club)

    # The schedule the button was pressed under is updated in place.
    assert chat.shown("ближайшие турниры") == (
        "Покер-клуб «Обь», ближайшие турниры:\n"
        "сб 3 октября, 19:00 — Субботний турнир, бай-ин 2 000 ₽ — вы записаны"
    )
    assert chat.buttons_under("ближайшие турниры") == ["Отменить запись: 3.10 Субботний турнир"]


def test_a_player_drops_out_from_the_schedule(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    url = signed_up(chat, client, club)

    reply = chat.press("Отменить запись: 3.10 Субботний турнир")

    assert "Запись на турнир «Субботний турнир» отменена" in reply
    assert registered_names(client, url) == []
    assert chat.buttons_under("ближайшие турниры") == ["Записаться: 3.10 Субботний турнир"]


def test_a_player_cannot_sign_up_twice(chat: BotChat, client: TestClient, club: Club) -> None:
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир")
    ).json()
    go_through_the_bot(chat)
    # Two schedules: the button under the first one is pressed, the second one is left as it was.
    chat.send("/schedule")
    chat.send("/schedule")
    chat.press("Записаться: 3.10 Субботний турнир")
    chat.send("/schedule")
    chat.send("Привет")

    reply = chat.press("Записаться: 3.10 Субботний турнир")

    assert reply == "Вы уже записаны на турнир «Субботний турнир»."
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    assert registered_names(client, url) == ["Мария Иванова"]


def test_a_player_cannot_sign_up_for_a_started_tournament_without_late_registration(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(
        client, club, arrived=2, name="Вечерний турнир", late_registration_until_level=None
    )
    go_through_the_bot(chat)
    chat.send("/schedule")
    client.post(f"{url}/start")

    reply = chat.press("Записаться: 27.09 Вечерний турнир")

    assert reply == "Турнир уже идёт, поздней регистрации в нём нет"
    assert "Мария Иванова" not in registered_names(client, url)
    assert "Вечерний турнир" not in chat.shown("Покер-клуб «Обь»")


def test_a_started_tournament_with_late_registration_open_is_in_the_schedule_to_sign_up_for(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=2, name="Вечерний турнир")
    client.post(f"{url}/start")
    go_through_the_bot(chat)

    reply = chat.send("/schedule")
    assert (
        "вс 27 сентября, 02:00 — Вечерний турнир, бай-ин 2 000 ₽ — "
        "идёт, поздняя регистрация до уровня 3"
    ) in reply
    chat.press("Записаться: 27.09 Вечерний турнир")

    assert "Мария Иванова" in registered_names(client, url)


def bot_player_id(client: TestClient, club: Club) -> int:
    """The club player the bot linked, Мария Иванова, as the admin panel knows her."""
    club_players = client.get(f"/api/clubs/{club.id}/players").json()
    return int(next(p["id"] for p in club_players if p["name"] == "Мария Иванова"))


def has_come(client: TestClient, club: Club, tournament_url: str) -> int:
    """The club registers the bot's player, Мария Иванова, for the tournament and checks her in;
    returns her player id."""
    maria = bot_player_id(client, club)
    client.post(f"{tournament_url}/registrations", json={"player_id": maria})
    client.post(f"{tournament_url}/registrations/{maria}/check-in", json=CASH)
    return maria


def test_rating_shows_the_players_position_and_points_and_the_clubs_top_ten(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    go_through_the_bot(chat)
    # Twelve players: Мария Иванова is knocked out second, so she finishes 11th with 0 points.
    url, guests = ready_tournament(client, club, arrived=11)
    maria = has_come(client, club, url)
    client.post(f"{url}/start")
    knock_out(client, url, guests[0], {"id": maria}, *guests[1:10])

    reply = chat.send("/rating")

    # Points for 12 players: 25, 14, 10, 7, 5, 4, 3, 2, 2, 1, 0, 0 from the winner down.
    assert reply == (
        "Рейтинг клуба Покер-клуб «Обь», 2-е полугодие 2026\n"
        "Ваше место: 11, очков: 0, турниров: 1\n"
        "\n"
        "Топ-10:\n"
        "1. Гость 11 — 25\n"
        "2. Гость 10 — 14\n"
        "3. Гость 09 — 10\n"
        "4. Гость 08 — 7\n"
        "5. Гость 07 — 5\n"
        "6. Гость 06 — 4\n"
        "7. Гость 05 — 3\n"
        "8. Гость 03 — 2\n"
        "8. Гость 04 — 2\n"
        "10. Гость 02 — 1"
    )


def test_rating_tells_a_player_without_results_that_they_are_not_in_it_yet(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    played_tournament(client, club, players=2)
    go_through_the_bot(chat)

    reply = chat.send("/rating")

    assert reply == (
        "Рейтинг клуба Покер-клуб «Обь», 2-е полугодие 2026\n"
        "Вас пока нет в рейтинге: сыграйте в турнире клуба в этом сезоне.\n"
        "\n"
        "Топ-10:\n"
        "1. Гость 02 — 4\n"
        "2. Гость 01 — 0"
    )


def test_rating_of_a_club_with_no_finished_tournaments_this_season(
    chat: BotChat, club: Club
) -> None:
    go_through_the_bot(chat)

    reply = chat.send("/rating")

    assert reply == (
        "Рейтинг клуба Покер-клуб «Обь», 2-е полугодие 2026\n"
        "В этом сезоне турниры клуба ещё не завершались, рейтинг пуст."
    )


def test_a_signed_up_player_is_reminded_of_the_tournament_as_long_before_as_set_once(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    # Starts a week after the clock's now.
    signed_up(chat, client, club)
    three_hours = timedelta(hours=3)

    clock.advance(timedelta(days=7) - three_hours - timedelta(minutes=1))
    assert chat.check_notifications(remind_before=three_hours) == ""
    clock.advance(timedelta(minutes=1))
    assert chat.check_notifications(remind_before=three_hours) == (
        "Напоминаем: вы записаны на турнир «Субботний турнир», сб 3 октября, 19:00, "
        "Покер-клуб «Обь». Бай-ин 2 000 ₽ оплачивается в клубе. "
        "Если не сможете прийти, отмените запись: /schedule"
    )
    clock.advance(timedelta(minutes=30))
    assert chat.check_notifications(remind_before=three_hours) == ""


def test_players_the_club_registered_are_reminded_too_if_their_telegram_is_linked(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир")
    ).json()
    go_through_the_bot(chat)
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    client.post(f"{url}/registrations", json={"player_id": bot_player_id(client, club)})

    clock.advance(timedelta(days=7) - timedelta(hours=2))

    assert "Напоминаем: вы записаны на турнир «Субботний турнир»" in chat.check_notifications()


def test_no_reminder_for_a_cancelled_tournament_or_after_dropping_out(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    url = signed_up(chat, client, club)
    client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Второй турнир"))
    chat.send("/schedule")
    chat.press("Записаться: 3.10 Второй турнир")
    chat.press("Отменить запись: 3.10 Второй турнир")
    client.post(f"{url}/cancel")

    clock.advance(timedelta(days=7) - timedelta(hours=1))

    assert chat.check_notifications() == ""


def test_no_reminder_for_signing_up_when_the_tournament_is_about_to_start(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир"))
    clock.advance(timedelta(days=7) - timedelta(hours=1))
    go_through_the_bot(chat)
    chat.send("/schedule")
    chat.press("Записаться: 3.10 Субботний турнир")

    assert chat.check_notifications() == ""


def test_after_the_tournament_finishes_the_player_gets_their_place_and_points_once(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    go_through_the_bot(chat)
    url, guests = ready_tournament(client, club, arrived=2, name="Вечерний турнир")
    maria = has_come(client, club, url)
    client.post(f"{url}/start")
    assert chat.check_notifications() == ""

    # Of three players Мария Иванова finishes second: 10 × (√(3 ÷ 2) − 1) ≈ 2 points.
    knock_out(client, url, guests[0], {"id": maria})

    assert chat.check_notifications() == (
        "Турнир «Вечерний турнир» завершён. Ваше место: 2 из 3, очков в рейтинг клуба: 2. "
        "Рейтинг клуба: /rating"
    )
    assert chat.check_notifications() == ""


def test_results_of_a_tournament_finished_over_a_day_ago_are_not_sent(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    go_through_the_bot(chat)
    url, guests = ready_tournament(client, club, arrived=1)
    has_come(client, club, url)
    client.post(f"{url}/start")
    knock_out(client, url, guests[0])

    clock.advance(timedelta(days=1, minutes=1))

    assert chat.check_notifications() == ""


def test_the_bot_keeps_quiet_in_group_chats(clock: FakeClock) -> None:
    group = BotChat(clock, chat_type="group")

    group.send("/start")
    group.send("Всем привет!")

    assert group.replies == []


def test_a_phone_that_is_not_russian_is_not_taken(chat: BotChat) -> None:
    agree(chat)

    reply = chat.share_contact("+380501234567")

    assert "только с российскими номерами" in reply
    assert chat.contact_button_removed()


def test_someone_elses_contact_is_not_taken(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    agree(chat)

    reply = chat.share_contact("+79135551234", first_name="Сосед", user_id=777)

    assert "Отправьте свой номер" in reply
    assert chat.asks_for_contact()
    added = client.post(f"/api/clubs/{club.id}/players", json=a_player(phone="+79135551234"))
    assert added.json()["outcome"] == "created"


def test_no_drop_out_button_where_the_bot_would_refuse_it(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    # One the player has come to (and paid for), one going on with late registration open.
    tonight, _ = ready_tournament(client, club, arrived=0, name="Вечерний турнир")
    live, _ = ready_tournament(client, club, arrived=2, name="Идущий турнир")
    client.post(f"{live}/start")
    go_through_the_bot(chat)
    maria = bot_player_id(client, club)
    for url in (tonight, live):
        client.post(f"{url}/registrations", json={"player_id": maria})
    client.post(f"{tonight}/registrations/{maria}/check-in", json=CASH)

    chat.send("/schedule")

    assert chat.buttons_under("ближайшие турниры") == []
    schedule = chat.shown("ближайшие турниры")
    assert "Вечерний турнир, бай-ин 2 000 ₽ — вы записаны" in schedule
    assert "Идущий турнир, бай-ин 2 000 ₽ — идёт, поздняя регистрация до уровня 3 — вы записаны" in schedule


def test_a_player_who_has_come_to_the_club_is_not_reminded(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    url, _ = ready_tournament(client, club, arrived=0)
    go_through_the_bot(chat)
    has_come(client, club, url)

    # Tonight's tournament starts at 19:00 UTC, seven hours after the clock's now.
    clock.advance(timedelta(hours=6))

    assert chat.check_notifications() == ""


def test_a_tournament_moved_to_a_later_start_is_reminded_of_again(
    chat: BotChat, client: TestClient, club: Club, clock: FakeClock
) -> None:
    url = signed_up(chat, client, club)
    clock.advance(timedelta(days=7) - timedelta(hours=2))
    chat.check_notifications()

    client.put(url, json=a_tournament(name="Субботний турнир", starts_at="2026-10-04T19:00:00+07:00"))
    clock.advance(timedelta(days=1))

    assert "вс 4 октября, 19:00" in chat.check_notifications()


def test_the_top_ten_takes_in_everyone_sharing_the_tenth_position(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    # Of eleven players the last two both get 0 points and share the 10th position.
    played_tournament(client, club, players=11)
    go_through_the_bot(chat)

    lines = chat.send("/rating").splitlines()

    assert lines[-2:] == ["10. Гость 01 — 0", "10. Гость 02 — 0"]


def test_a_sign_up_is_confirmed_even_when_the_schedule_can_no_longer_be_edited(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир"))
    go_through_the_bot(chat)
    chat.send("/schedule")
    chat.telegram.refuse_edits = True

    reply = chat.press("Записаться: 3.10 Субботний турнир")

    assert "Вы записаны на турнир «Субботний турнир»" in reply
    # The schedule as it is now comes as a new message instead.
    assert "Субботний турнир, бай-ин 2 000 ₽ — вы записаны" in reply
