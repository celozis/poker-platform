"""Runs the Telegram bot by long polling, which needs no public address: enough for the local
prototype. Deployment will switch to a webhook. Alongside the answers it sends the reminders and
results due (app/bot/notifications.py).

    TELEGRAM_BOT_TOKEN=... [BOT_REMINDER_MINUTES=120] python -m app.bot
"""

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.types import BotCommand

from app.auth import get_clock
from app.bot.notifications import notify_forever
from app.bot.telegram import create_dispatcher
from app.config import reminder_before

logger = logging.getLogger("app.bot")

COMMANDS = [
    BotCommand(command="schedule", description="Ближайшие турниры моего клуба"),
    BotCommand(command="rating", description="Мой рейтинг в клубе и топ-10"),
    BotCommand(command="club", description="Сменить клуб"),
    BotCommand(command="start", description="Начать сначала"),
]


async def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.warning(
            "Бот не запущен: нет токена. Создайте бота у @BotFather в Telegram и впишите "
            "TELEGRAM_BOT_TOKEN=<токен> в файл .env в корне проекта, затем: docker compose up -d bot"
        )
        return
    bot = Bot(token)
    # The menu of commands next to the message field.
    await bot.set_my_commands(COMMANDS)
    clock = get_clock()
    # Reminders and results, alongside the answers; kept referenced so it is not collected.
    notifying = asyncio.create_task(notify_forever(bot, clock, reminder_before()))
    try:
        await create_dispatcher(clock).start_polling(bot)
    finally:
        notifying.cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
    asyncio.run(main())
