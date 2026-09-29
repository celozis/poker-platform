"""Runs the Telegram bot by long polling, which needs no public address: enough for the local
prototype. Deployment will switch to a webhook.

    TELEGRAM_BOT_TOKEN=... python -m app.bot
"""

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.types import BotCommand

from app.auth import get_clock
from app.bot.telegram import create_dispatcher

logger = logging.getLogger("app.bot")

COMMANDS = [
    BotCommand(command="schedule", description="Ближайшие турниры моего клуба"),
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
    await create_dispatcher(get_clock()).start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
    asyncio.run(main())
