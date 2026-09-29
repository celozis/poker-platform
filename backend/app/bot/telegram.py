"""The Telegram side of the bot (aiogram): turns what the player sends into steps of
app/bot/conversation.py and sends its replies back. Only private chats are answered, so the chat
of a message and the user who pressed a button are the same Telegram user."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Concatenate

from aiogram import Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from app.bot import conversation
from app.bot.conversation import ClubChoice, ConsentAnswer, Reply
from app.db import SessionLocal
from app.models import TelegramUser

# Tells the time: app.auth.get_clock() in the bot, a fake clock in tests.
TimeSource = Callable[[], datetime]


async def _run_step[**P](
    step: Callable[Concatenate[Session, TelegramUser, P], list[Reply]],
    telegram_id: int,
    *args: P.args,
    **kwargs: P.kwargs,
) -> list[Reply]:
    """Runs a step of the conversation for the Telegram user in its own session and commits it.
    In a thread: the database code is sync (ADR-0002) and must not hold up the bot's other chats."""

    def run() -> list[Reply]:
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


async def on_schedule(message: Message, clock: TimeSource) -> None:
    await _send(message, await _run_step(conversation.schedule, message.chat.id, clock()))


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
    router.message.register(on_club, Command("club"))
    router.callback_query.register(on_consent, ConsentAnswer.filter())
    router.callback_query.register(on_club_chosen, ClubChoice.filter())
    router.message.register(on_contact, F.contact)
    # Last: whatever no handler above takes.
    router.message.register(on_anything_else)

    dispatcher = Dispatcher(clock=clock)
    dispatcher.include_router(router)
    return dispatcher
