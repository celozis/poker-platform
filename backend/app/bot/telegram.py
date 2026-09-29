"""The Telegram side of the bot (aiogram): turns what the player sends into steps of
app/bot/conversation.py and sends its replies back. Only private chats are answered, so the chat
of a message and the user who pressed a button are the same Telegram user."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Concatenate

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.orm import Session

from app.bot import conversation
from app.bot.conversation import (
    ClubChoice,
    ConsentAnswer,
    DropOutRequest,
    Reply,
    ScheduleChange,
    SignUpRequest,
)
from app.db import SessionLocal
from app.models import TelegramUser

# Tells the time: app.auth.get_clock() in the bot, a fake clock in tests.
TimeSource = Callable[[], datetime]


async def _run_step[**P, R](
    step: Callable[Concatenate[Session, TelegramUser, P], R],
    telegram_id: int,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Runs a step of the conversation for the Telegram user in its own session and commits it.
    In a thread: the database code is sync (ADR-0002) and must not hold up the bot's other chats."""

    def run() -> R:
        with SessionLocal() as session:
            replies = step(session, conversation.telegram_user(session, telegram_id), *args, **kwargs)
            session.commit()
            return replies

    return await asyncio.to_thread(run)


async def _send(message: Message, replies: list[Reply]) -> None:
    for reply in replies:
        await message.answer(reply.text, reply_markup=reply.markup)


async def _answer_button(callback: CallbackQuery, replies: list[Reply]) -> None:
    """Answers a pressed button and takes the buttons off its message, so it is pressed once."""
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await _send(callback.message, replies)


async def on_start(message: Message) -> None:
    await _send(message, await _run_step(conversation.start, message.chat.id))


async def on_consent(
    callback: CallbackQuery, callback_data: ConsentAnswer, clock: TimeSource
) -> None:
    replies = await _run_step(
        conversation.answer_consent, callback.from_user.id, callback_data.agreed, clock()
    )
    await _answer_button(callback, replies)


async def on_contact(message: Message, clock: TimeSource) -> None:
    assert message.contact is not None  # the handler's filter
    replies = await _run_step(
        conversation.share_contact, message.chat.id, message.contact, clock()
    )
    await _send(message, replies)


async def on_club_chosen(
    callback: CallbackQuery, callback_data: ClubChoice, clock: TimeSource
) -> None:
    replies = await _run_step(
        conversation.choose_club, callback.from_user.id, callback_data.club_id, clock()
    )
    await _answer_button(callback, replies)


async def _shown_in_place(message: Message | None, schedule: Reply | None) -> bool:
    """Shows the schedule afresh in place of the message the button was pressed under, or takes
    the buttons off it when there is no schedule. False when Telegram no longer lets the message
    be edited: it is too old or gone."""
    if message is None:
        return False
    try:
        if schedule is None:
            await message.edit_reply_markup(reply_markup=None)
        else:
            # A message keeps only inline buttons, the only ones a schedule has.
            markup = schedule.markup
            await message.edit_text(
                schedule.text,
                reply_markup=markup if isinstance(markup, InlineKeyboardMarkup) else None,
            )
    except TelegramBadRequest as error:
        # Telegram refuses an edit that changes nothing, as when a button is pressed twice.
        return "message is not modified" in error.message
    return True


async def _answer_schedule_button(
    callback: CallbackQuery, bot: Bot, change: ScheduleChange
) -> None:
    """Answers a button under the schedule: the schedule is shown afresh in its place, so its
    buttons stay right, and the replies follow. The change is made already, so the replies go
    whatever happens to the old message; the schedule then comes as a new one."""
    await callback.answer()
    message = callback.message if isinstance(callback.message, Message) else None
    replies = change.replies
    if not await _shown_in_place(message, change.schedule) and change.schedule is not None:
        replies = [*replies, change.schedule]
    for reply in replies:
        await bot.send_message(callback.from_user.id, reply.text, reply_markup=reply.markup)


async def on_sign_up(
    callback: CallbackQuery, callback_data: SignUpRequest, bot: Bot, clock: TimeSource
) -> None:
    change = await _run_step(
        conversation.sign_up, callback.from_user.id, callback_data.tournament_id, clock()
    )
    await _answer_schedule_button(callback, bot, change)


async def on_drop_out(
    callback: CallbackQuery, callback_data: DropOutRequest, bot: Bot, clock: TimeSource
) -> None:
    change = await _run_step(
        conversation.drop_out, callback.from_user.id, callback_data.tournament_id, clock()
    )
    await _answer_schedule_button(callback, bot, change)


async def on_schedule(message: Message, clock: TimeSource) -> None:
    await _send(message, await _run_step(conversation.schedule, message.chat.id, clock()))


async def on_rating(message: Message, clock: TimeSource) -> None:
    await _send(message, await _run_step(conversation.rating, message.chat.id, clock()))


async def on_club(message: Message) -> None:
    await _send(message, await _run_step(conversation.change_club, message.chat.id))


async def on_anything_else(message: Message) -> None:
    await _send(message, await _run_step(conversation.current_step, message.chat.id))


def create_dispatcher(clock: TimeSource) -> Dispatcher:
    """The bot's dispatcher. Handlers are registered on a router of its own: a router can belong
    to one dispatcher only."""
    router = Router()
    # Only private chats: in a group the bot would answer everyone's every message.
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.message.register(on_start, CommandStart())
    router.message.register(on_schedule, Command("schedule"))
    router.message.register(on_rating, Command("rating"))
    router.message.register(on_club, Command("club"))
    router.callback_query.register(on_consent, ConsentAnswer.filter())
    router.callback_query.register(on_club_chosen, ClubChoice.filter())
    router.callback_query.register(on_sign_up, SignUpRequest.filter())
    router.callback_query.register(on_drop_out, DropOutRequest.filter())
    router.message.register(on_contact, F.contact)
    # Last: whatever no handler above takes.
    router.message.register(on_anything_else)

    dispatcher = Dispatcher(clock=clock)
    dispatcher.include_router(router)
    return dispatcher
