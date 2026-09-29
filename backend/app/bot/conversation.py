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

from app.auth import normalize_phone
from app.models import Club, TelegramUser, Tournament
from app.players import add_to_club_list, league_player
from app.registrations import CHECK_IN_WINDOW
from app.seasons import LEAGUE_TIME

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
# The soonest tournaments the schedule shows: enough for a couple of weeks, and one message
# stays well within Telegram's 4096 characters.
SCHEDULE_LENGTH = 10
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


def _date_and_time(moment: datetime) -> str:
    """"пт 2 октября, 19:30", in the league's time: the clubs have no time zone of their own yet."""
    local = moment.astimezone(LEAGUE_TIME)
    return f"{WEEKDAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, {local:%H:%M}"


def _roubles(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"


def schedule(session: Session, user: TelegramUser, now: datetime) -> list[Reply]:
    """The tournaments of the player's club that have not started yet, the soonest first. One the
    admin has neither started nor cancelled goes once the player can no longer come to it: its
    check-in closes CHECK_IN_WINDOW after its start."""
    if user.club is None:
        return current_step(session, user)
    tournaments = session.scalars(
        select(Tournament)
        .where(
            Tournament.club_id == user.club.id,
            Tournament.status == "scheduled",
            Tournament.starts_at >= now - CHECK_IN_WINDOW,
        )
        .order_by(Tournament.starts_at, Tournament.id)
        .limit(SCHEDULE_LENGTH)
    )
    lines = [
        f"{_date_and_time(t.starts_at)} — {t.name}, бай-ин {_roubles(t.buy_in)}"
        for t in tournaments
    ]
    if not lines:
        return [Reply(f"У клуба {user.club.name} пока нет запланированных турниров.")]
    return [Reply("\n".join([f"{user.club.name}, ближайшие турниры:", *lines]))]
