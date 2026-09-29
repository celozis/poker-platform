"""The Telegram bot: a player links their Telegram to their player by phone and sees the
tournaments of their club. Updates go through the bot's real dispatcher into the test database;
Telegram itself is replaced by tests/bot.py, and the admin API shows what the bot has done."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.bot import BotChat
from tests.clock import FakeClock
from tests.factories import create_club
from tests.game import ready_tournament
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


def agree(chat: BotChat) -> None:
    chat.send("/start")
    chat.press("Согласен")


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


def go_through_the_bot(chat: BotChat, club: str = "Покер-клуб «Обь»") -> None:
    """Goes through the whole sign-up: consent, the phone +7 913 555-12-34, the club."""
    agree(chat)
    chat.share_contact("+79135551234", first_name="Мария", last_name="Иванова")
    chat.press(club)


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
    started, _ = ready_tournament(client, club, arrived=2, name="Идущий турнир")
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
