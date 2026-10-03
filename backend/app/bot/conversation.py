"""What the bot answers. A player goes through the steps in order: agree to the processing of
personal data, share their phone, which links their Telegram to their player, and choose their
club; then they see the club's schedule. Whatever they send, the bot goes on from the first step
not yet done, as stored in their TelegramUser, so a restart of the bot loses nothing.

Each step takes the session and the Telegram user it answers, locked, and returns the replies;
app/bot/telegram.py commits. Sync, like the rest of the database code (ADR-0002), so
app/bot/telegram.py runs the steps in a thread."""

from dataclasses import dataclass
from datetime import datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    Contact,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import action_log, realtime
from app.auth import normalize_phone
from app.models import Club, Registration, TelegramUser, Tournament
from app.players import add_to_club_list, league_player
from app.registrations import (
    closed_to_players_before_start,
    dropping_out_closed_because,
    find_registration,
    player_registration_closed_because,
)
from app.rating import club_standings
from app.schedule import club_schedule
from app.seasons import LEAGUE_TIME, season_at
from app.transactions import roubles

GREETING = (
    "Здравствуйте! Это бот Сибирской лиги покера. "
    "Здесь вы увидите расписание турниров своего клуба."
)
CONSENT_REQUEST = (
    "Чтобы продолжить, дайте согласие на обработку персональных данных (152-ФЗ): "
    "лига и её клубы будут хранить ваше имя, телефон и Telegram, "
    "чтобы записывать вас на турниры и вести рейтинг."
)
CONSENT_REFUSED = (
    "Без согласия на обработку персональных данных бот не может продолжить. "
    "Если передумаете, нажмите /start."
)
CONTACT_REQUEST = (
    "Спасибо! Теперь поделитесь номером телефона кнопкой «Поделиться контактом» внизу: "
    "по нему мы найдём вашу карточку игрока или заведём новую."
)
NOT_OWN_CONTACT = "Это чужой контакт. Отправьте свой номер кнопкой «Поделиться контактом» внизу."
NOT_RUSSIAN_PHONE = (
    "Пока бот работает только с российскими номерами (+7). "
    "Чтобы записаться на турнир, обратитесь к администратору клуба."
)
CLUB_REQUEST = "Выберите свой клуб:"
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


class ConsentAnswer(CallbackData, prefix="consent"):
    """What a pressed consent button sends back."""

    agreed: bool


class ClubChoice(CallbackData, prefix="club"):
    """What a pressed club button sends back."""

    club_id: int


class SignUpRequest(CallbackData, prefix="sign_up"):
    """What a pressed sign-up button under the schedule sends back."""

    tournament_id: int


class DropOutRequest(CallbackData, prefix="drop_out"):
    """What a pressed drop-out button under the schedule sends back."""

    tournament_id: int


@dataclass(frozen=True)
class Reply:
    text: str
    markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None = None


def telegram_user(session: Session, telegram_id: int) -> TelegramUser:
    """The stored Telegram user, locked, so that two of their messages at once are answered one
    after the other; stored when they first write to the bot."""
    session.execute(insert(TelegramUser).values(telegram_id=telegram_id).on_conflict_do_nothing())
    user = session.get(TelegramUser, telegram_id, with_for_update=True)
    assert user is not None
    return user


def _consent_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Согласен", callback_data=ConsentAnswer(agreed=True).pack()
                ),
                InlineKeyboardButton(
                    text="Не согласен", callback_data=ConsentAnswer(agreed=False).pack()
                ),
            ]
        ]
    )


def _contact_button() -> ReplyKeyboardMarkup:
    """Telegram sends the user's own phone number, confirmed by Telegram, when this is pressed."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _club_request(session: Session) -> list[Reply]:
    clubs = session.scalars(select(Club).order_by(Club.name, Club.id))
    buttons = [
        [InlineKeyboardButton(text=club.name, callback_data=ClubChoice(club_id=club.id).pack())]
        for club in clubs
    ]
    return [Reply(CLUB_REQUEST, InlineKeyboardMarkup(inline_keyboard=buttons))]


def current_step(session: Session, user: TelegramUser) -> list[Reply]:
    """The first step the player has not done yet; also the answer to anything unexpected."""
    if user.consent_given_at is None:
        return [Reply(CONSENT_REQUEST, _consent_buttons())]
    if user.player is None:
        return [Reply(CONTACT_REQUEST, _contact_button())]
    if user.club is None:
        return _club_request(session)
    return [
        Reply(
            f"Вы — {user.player.name}, ваш клуб: {user.club.name}. "
            "Расписание его турниров: /schedule"
        )
    ]


def start(session: Session, user: TelegramUser) -> list[Reply]:
    return [Reply(GREETING), *current_step(session, user)]


def answer_consent(
    session: Session, user: TelegramUser, agreed: bool, now: datetime
) -> list[Reply]:
    if agreed and user.consent_given_at is None:
        user.consent_given_at = now
    if user.consent_given_at is None:
        return [Reply(CONSENT_REFUSED)]
    return current_step(session, user)


def share_contact(
    session: Session, user: TelegramUser, contact: Contact, now: datetime
) -> list[Reply]:
    """Links the Telegram account to the player with the shared phone, or to a new player named
    as in Telegram. A player who has chosen their club is on its list, whichever player the
    account is linked to."""
    if user.consent_given_at is None:
        return current_step(session, user)
    if contact.user_id != user.telegram_id:
        # Only the user's own contact: Telegram has confirmed that phone is theirs.
        return [Reply(NOT_OWN_CONTACT, _contact_button())]
    phone = normalize_phone(contact.phone_number)
    if phone is None:
        return [Reply(NOT_RUSSIAN_PHONE, ReplyKeyboardRemove())]

    name = " ".join(filter(None, [contact.first_name, contact.last_name]))
    player, created = league_player(session, name, phone, user.consent_given_at)
    # The phone is this account's now, so it takes the player over from an account that had it.
    session.execute(
        update(TelegramUser)
        .where(TelegramUser.player_id == player.id, TelegramUser.telegram_id != user.telegram_id)
        .values(player_id=None)
    )
    user.player = player
    if user.club is not None:
        add_to_club_list(session, user.club.id, player, now)
    found = (
        f"Готово, вы в базе лиги: {player.name}."
        if created
        else f"Нашли вашу карточку игрока: {player.name}. Telegram привязан к ней."
    )
    return [Reply(found, ReplyKeyboardRemove()), *current_step(session, user)]


def change_club(session: Session, user: TelegramUser) -> list[Reply]:
    """Offers the clubs again, once the player has got as far as choosing one."""
    if user.player is None:
        return current_step(session, user)
    return _club_request(session)


def choose_club(
    session: Session, user: TelegramUser, club_id: int, now: datetime
) -> list[Reply]:
    """Makes the club the player's own: the bot shows its tournaments, and the player joins the
    club's player list, where its admins see them."""
    club = session.get(Club, club_id)
    if user.player is None or club is None:
        return current_step(session, user)
    user.club = club
    add_to_club_list(session, club.id, user.player, now)
    return [Reply(f"Ваш клуб: {club.name}. Расписание его турниров: /schedule")]


def date_and_time(moment: datetime) -> str:
    """"пт 2 октября, 19:30", in the league's time: the clubs have no time zone of their own yet."""
    local = moment.astimezone(LEAGUE_TIME)
    return f"{WEEKDAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, {local:%H:%M}"


def _short_date(moment: datetime) -> str:
    """"3.10", in the league's time: a button has room for little more than the name."""
    local = moment.astimezone(LEAGUE_TIME)
    return f"{local.day}.{local.month:02}"


def _schedule(session: Session, user: TelegramUser, club: Club, now: datetime) -> Reply:
    """The club's schedule (app/schedule.py), each tournament with a button to sign up or, for one
    the player is signed up for, to drop out."""
    tournaments = club_schedule(session, club.id, now)
    if not tournaments:
        return Reply(f"У клуба {club.name} пока нет запланированных турниров.")
    # The player's registrations for these tournaments: whether they have come, by tournament.
    came = {
        tournament_id: checked_in_at
        for tournament_id, checked_in_at in session.execute(
            select(Registration.tournament_id, Registration.checked_in_at).where(
                Registration.player_id == user.player_id,
                Registration.tournament_id.in_([t.id for t in tournaments]),
            )
        )
    }
    lines = [f"{club.name}, ближайшие турниры:"]
    buttons = []
    for t in tournaments:
        line = f"{date_and_time(t.starts_at)} — {t.name}, бай-ин {roubles(t.buy_in)}"
        if t.is_live:
            line += f" — идёт, поздняя регистрация до уровня {t.late_registration_until_level}"
        label = f"{_short_date(t.starts_at)} {t.name}"
        if t.id not in came and closed_to_players_before_start(t):
            lines.append(f"{line} — запись закрыта")
            continue
        if t.id not in came:
            lines.append(line)
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Записаться: {label}",
                        callback_data=SignUpRequest(tournament_id=t.id).pack(),
                    )
                ]
            )
            continue
        lines.append(f"{line} — вы записаны")
        # Once it has started, or once the player has come and paid, only the admin takes them off.
        if not t.is_live and came[t.id] is None:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"Отменить запись: {label}",
                        callback_data=DropOutRequest(tournament_id=t.id).pack(),
                    )
                ]
            )
    return Reply(
        "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    )


def schedule(session: Session, user: TelegramUser, now: datetime) -> list[Reply]:
    if user.club is None:
        return current_step(session, user)
    return [_schedule(session, user, user.club, now)]


@dataclass(frozen=True)
class ScheduleChange:
    """What a sign-up or drop-out button under the schedule answers: the replies, and the schedule
    as it is now, to be shown in place of the one the button was pressed under. No schedule when
    the player has not got that far."""

    replies: list[Reply]
    schedule: Reply | None = None


def _with_schedule(
    session: Session, user: TelegramUser, now: datetime, *replies: Reply
) -> ScheduleChange:
    if user.club is None:
        return ScheduleChange(current_step(session, user))
    return ScheduleChange(list(replies), _schedule(session, user, user.club, now))


def sign_up(
    session: Session, user: TelegramUser, tournament_id: int, now: datetime
) -> ScheduleChange:
    """Registers the player for a tournament of their club, by the rules the admin panel keeps:
    until the start, or afterwards while late registration is open, and once; but not once the
    admin has closed registration to players."""
    if user.player is None or user.club is None:
        return ScheduleChange(current_step(session, user))
    tournament = session.get(Tournament, tournament_id, with_for_update=True)
    if tournament is None or tournament.club_id != user.club.id:
        return _with_schedule(session, user, now, Reply("Это турнир не вашего клуба."))
    closed = player_registration_closed_because(tournament, now)
    if closed:
        return _with_schedule(session, user, now, Reply(closed))
    # The tournament row is locked, so a second press at once waits here and finds this one.
    if find_registration(session, tournament.id, user.player.id) is not None:
        return _with_schedule(
            session, user, now, Reply(f"Вы уже записаны на турнир «{tournament.name}».")
        )
    session.add(
        Registration(
            club_id=tournament.club_id,
            tournament_id=tournament.id,
            player_id=user.player.id,
            registered_at=now,
        )
    )
    action_log.record(session, tournament, None, "registered", now, player_id=user.player.id)
    session.flush()
    # The admin panel shows the player at once, although the bot is a process of its own.
    realtime.tournament_changed(session, tournament.id)
    signed = Reply(
        f"Вы записаны на турнир «{tournament.name}», {date_and_time(tournament.starts_at)}. "
        "Бай-ин оплачивается в клубе, когда придёте."
    )
    return _with_schedule(session, user, now, signed)


def drop_out(
    session: Session, user: TelegramUser, tournament_id: int, now: datetime
) -> ScheduleChange:
    """Takes the player off a tournament before its start. Not once they have come and paid the
    buy-in: giving it back is the admin's, in the club."""
    if user.player is None:
        return ScheduleChange(current_step(session, user))
    tournament = session.get(Tournament, tournament_id, with_for_update=True)
    registration = (
        None if tournament is None else find_registration(session, tournament.id, user.player.id)
    )
    if tournament is None or registration is None:
        return _with_schedule(session, user, now, Reply("Вы не записаны на этот турнир."))
    closed = dropping_out_closed_because(tournament)
    if closed:
        return _with_schedule(session, user, now, Reply(closed))
    if registration.checked_in_at is not None:
        paid = Reply(
            "Вы уже отметились в клубе и оплатили бай-ин: "
            "снять запись и вернуть деньги может администратор клуба."
        )
        return _with_schedule(session, user, now, paid)
    session.delete(registration)
    action_log.record(
        session, tournament, None, "registration_cancelled", now, player_id=user.player.id
    )
    session.flush()
    realtime.tournament_changed(session, tournament.id)
    return _with_schedule(session, user, now, Reply(f"Запись на турнир «{tournament.name}» отменена."))


# The club rating's first rows the bot shows: one message, easy to read on a phone.
RATING_TOP = 10


def rating(session: Session, user: TelegramUser, now: datetime) -> list[Reply]:
    """The player's position and points in their club's rating of the current season, and the
    club's top ten, as the admin panel's club rating has them."""
    if user.player is None or user.club is None:
        return current_step(session, user)
    season = season_at(now)
    standings = club_standings(session, user.club.id, season.starts_at, season.ends_at)
    title = f"Рейтинг клуба {user.club.name}, {season.name}"
    if not standings:
        return [Reply(f"{title}\nВ этом сезоне турниры клуба ещё не завершались, рейтинг пуст.")]
    own = next((row for row in standings if row.player.id == user.player.id), None)
    position = (
        "Вас пока нет в рейтинге: сыграйте в турнире клуба в этом сезоне."
        if own is None
        else f"Ваше место: {own.position}, очков: {own.points}, турниров: {own.tournaments}"
    )
    # Everyone sharing the last position shown is shown.
    top = [
        f"{row.position}. {row.player.name} — {row.points}"
        for row in standings
        if row.position <= RATING_TOP
    ]
    return [Reply("\n".join([title, position, "", f"Топ-{RATING_TOP}:", *top]))]
