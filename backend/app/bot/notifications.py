"""What the bot sends players by itself: a reminder of a tournament they are registered for, some
time before its start, and their place and points once it has finished. Only to players whose
Telegram is linked, and each once: the registration keeps when it was sent.

The bot checks what is due every NOTIFY_EVERY (`notify_forever`), so nothing is lost while it is
stopped: a reminder still due or a result still fresh goes out once it is back. A notice is
marked as sent before it is sent, so a failure to send (say, the player has blocked the bot) is
not tried again and again."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bot.conversation import date_and_time, roubles
from app.db import SessionLocal
from app.models import Club, Registration, TelegramUser, Tournament

logger = logging.getLogger("app.bot")

# How often the bot looks for notices due.
NOTIFY_EVERY = timedelta(seconds=30)
# Results of a tournament finished longer ago are not sent: the player has long heard them in the
# club, and a player who links their Telegram later is not sent their old results.
RESULTS_FRESH_FOR = timedelta(days=1)


@dataclass(frozen=True)
class Notice:
    telegram_id: int
    text: str


def _reminders(session: Session, now: datetime, remind_before: timedelta) -> list[Notice]:
    """Reminders of tournaments that start within `remind_before`, to players who registered
    before that: one who signed up only just now needs no reminder, nor does one who has already
    come to the club."""
    rows = session.execute(
        select(Registration, Tournament, Club, TelegramUser.telegram_id)
        .join(Tournament, Tournament.id == Registration.tournament_id)
        .join(Club, Club.id == Tournament.club_id)
        .join(TelegramUser, TelegramUser.player_id == Registration.player_id)
        .where(
            Tournament.status == "scheduled",
            Tournament.starts_at > now,
            Tournament.starts_at <= now + remind_before,
            Registration.registered_at < Tournament.starts_at - remind_before,
            Registration.checked_in_at.is_(None),
            Registration.reminded_at.is_(None),
        )
        .with_for_update(of=Registration)
    ).all()
    notices = []
    for registration, tournament, club, telegram_id in rows:
        registration.reminded_at = now
        notices.append(
            Notice(
                telegram_id,
                f"Напоминаем: вы записаны на турнир «{tournament.name}», "
                f"{date_and_time(tournament.starts_at)}, {club.name}. "
                f"Бай-ин {roubles(tournament.buy_in)} оплачивается в клубе. "
                "Если не сможете прийти, отмените запись: /schedule",
            )
        )
    return notices


def _results(session: Session, now: datetime) -> list[Notice]:
    """Places and points of tournaments finished within RESULTS_FRESH_FOR."""
    rows = session.execute(
        select(Registration, Tournament, TelegramUser.telegram_id)
        .join(Tournament, Tournament.id == Registration.tournament_id)
        .join(TelegramUser, TelegramUser.player_id == Registration.player_id)
        .where(
            Tournament.status == "finished",
            Tournament.finished_at >= now - RESULTS_FRESH_FOR,
            Registration.place.is_not(None),
            Registration.result_sent_at.is_(None),
        )
        .with_for_update(of=Registration)
    ).all()
    # How many players finished each tournament, by its id.
    field_sizes: dict[int, int] = {}
    notices = []
    for registration, tournament, telegram_id in rows:
        if tournament.id not in field_sizes:
            field_sizes[tournament.id] = session.scalar(
                select(func.count()).where(
                    Registration.tournament_id == tournament.id, Registration.place.is_not(None)
                )
            ) or 0
        registration.result_sent_at = now
        notices.append(
            Notice(
                telegram_id,
                f"Турнир «{tournament.name}» завершён. "
                f"Ваше место: {registration.place} из {field_sizes[tournament.id]}, "
                f"очков в рейтинг клуба: {registration.points}. Рейтинг клуба: /rating",
            )
        )
    return notices


def _take_due(now: datetime, remind_before: timedelta) -> list[Notice]:
    """The notices due, marked as sent."""
    with SessionLocal() as session:
        notices = _reminders(session, now, remind_before) + _results(session, now)
        session.commit()
        return notices


async def send_notifications(bot: Bot, now: datetime, remind_before: timedelta) -> None:
    """Sends the reminders and the results due by `now`."""
    for notice in await asyncio.to_thread(_take_due, now, remind_before):
        try:
            await bot.send_message(notice.telegram_id, notice.text)
        except TelegramAPIError as error:
            logger.warning("Не отправлено игроку %s: %s", notice.telegram_id, error)


async def notify_forever(
    bot: Bot, clock: Callable[[], datetime], remind_before: timedelta
) -> None:
    """Sends what is due every NOTIFY_EVERY while the bot runs."""
    while True:
        try:
            await send_notifications(bot, clock(), remind_before)
        except Exception:
            # The database may be down for a while; the next round tries again.
            logger.exception("Уведомления не отправлены")
        await asyncio.sleep(NOTIFY_EVERY.total_seconds())
