import os
from datetime import timedelta


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://poker:poker@localhost:5433/poker",
    )


def reminder_before() -> timedelta:
    """How long before a tournament's start the Telegram bot reminds its registered players:
    BOT_REMINDER_MINUTES, two hours unless set."""
    return timedelta(minutes=int(os.environ.get("BOT_REMINDER_MINUTES", "120")))
