"""A player's chat with the Telegram bot, without the real Telegram: updates go straight into the
bot's dispatcher, and what the bot sends is recorded instead of being sent."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageReplyMarkup, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    Contact,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    User,
)

from app.bot.notifications import send_notifications
from app.bot.telegram import create_dispatcher
from tests.clock import FakeClock


class FakeTelegram(BaseSession):
    """Stands in for the Telegram Bot API at the bot's session: records every request the bot
    makes and answers it the way Telegram would, keeping the bot's messages as the user sees
    them, edits included."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        # The bot's messages by id, as they look now.
        self.messages: dict[int, Message] = {}
        # Telegram lets a message be edited for 48 hours only, and not once it is deleted.
        self.refuse_edits = False

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.requests.append(method)
        if isinstance(method, SendMessage):
            message = Message(
                message_id=len(self.requests),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
                reply_markup=method.reply_markup
                if isinstance(method.reply_markup, InlineKeyboardMarkup)
                else None,
            )
            self.messages[message.message_id] = message
            return message
        if isinstance(method, EditMessageText | EditMessageReplyMarkup):
            if self.refuse_edits:
                raise TelegramBadRequest(method, "Bad Request: message can't be edited")
            assert method.message_id is not None
            edited = self.messages[method.message_id]
            text = method.text if isinstance(method, EditMessageText) else edited.text
            self.messages[method.message_id] = edited.model_copy(
                update={"text": text, "reply_markup": method.reply_markup}
            )
            return self.messages[method.message_id]
        return True

    async def close(self) -> None:
        pass

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError
        yield b""


class BotChat:
    """A Telegram user's private chat with the bot. Each action returns once the bot has answered
    it; `replies` are the messages the bot sent in answer to the last action."""

    def __init__(
        self,
        clock: FakeClock,
        telegram_id: int = 5001,
        first_name: str = "Иван",
        last_name: str | None = "Петров",
        chat_type: str = "private",
    ) -> None:
        self.user = User(id=telegram_id, is_bot=False, first_name=first_name, last_name=last_name)
        # A private chat's id is the user's; a group's is its own (negative).
        self.chat = Chat(id=telegram_id if chat_type == "private" else -telegram_id, type=chat_type)
        self.telegram = FakeTelegram()
        self.bot = Bot("42:TEST", session=self.telegram)
        self.clock = clock
        self.dispatcher = create_dispatcher(clock)
        self.replies: list[SendMessage] = []
        self._updates = 0

    @property
    def reply(self) -> str:
        """Everything the bot said in answer to the last action, as one text."""
        return "\n".join(message.text for message in self.replies)

    def check_notifications(self, remind_before: timedelta = timedelta(hours=2)) -> str:
        """Lets the bot send what is due by the clock, as it does every so often by itself;
        returns what came to this chat, if anything."""
        sent_before = len(self.telegram.requests)
        asyncio.run(send_notifications(self.bot, self.clock(), remind_before))
        self.replies = [
            request
            for request in self.telegram.requests[sent_before:]
            if isinstance(request, SendMessage) and request.chat_id == self.user.id
        ]
        return self.reply

    def send(self, text: str) -> str:
        return self._feed(message=self._message(text=text))

    def share_contact(
        self,
        phone: str,
        first_name: str | None = None,
        last_name: str | None = None,
        user_id: int | None = None,
    ) -> str:
        """Shares a contact the way the contact button does: by default the user's own."""
        contact = Contact(
            phone_number=phone,
            first_name=first_name or self.user.first_name,
            last_name=last_name,
            user_id=self.user.id if user_id is None else user_id,
        )
        return self._feed(message=self._message(contact=contact))

    def press(self, button: str) -> str:
        """Presses the inline button with this text under the latest message that has it now."""
        for shown in reversed(self.telegram.messages.values()):
            for row in shown.reply_markup.inline_keyboard if shown.reply_markup else []:
                for candidate in row:
                    if candidate.text == button:
                        query = CallbackQuery(
                            id=f"query-{self._updates}",
                            from_user=self.user,
                            chat_instance="chat",
                            data=candidate.callback_data,
                            message=shown,
                        )
                        return self._feed(callback_query=query)
        raise AssertionError(f"No button {button!r} in the chat")

    def shown(self, fragment: str) -> str:
        """The latest of the bot's messages with this text in it, as it looks now."""
        for shown in reversed(self.telegram.messages.values()):
            if shown.text and fragment in shown.text:
                return shown.text
        raise AssertionError(f"No message with {fragment!r} in the chat")

    def buttons_under(self, fragment: str) -> list[str]:
        """The inline buttons under the latest message with this text in it, as it looks now."""
        for shown in reversed(self.telegram.messages.values()):
            if shown.text and fragment in shown.text:
                markup = shown.reply_markup
                return [b.text for row in markup.inline_keyboard for b in row] if markup else []
        raise AssertionError(f"No message with {fragment!r} in the chat")

    def buttons(self) -> list[str]:
        """The inline buttons under the bot's last message, if any."""
        markup = self.replies[-1].reply_markup if self.replies else None
        if not isinstance(markup, InlineKeyboardMarkup):
            return []
        return [button.text for row in markup.inline_keyboard for button in row]

    def asks_for_contact(self) -> bool:
        """Whether the bot's last message shows the button that shares the user's phone."""
        markup = self.replies[-1].reply_markup if self.replies else None
        return isinstance(markup, ReplyKeyboardMarkup) and any(
            button.request_contact for row in markup.keyboard for button in row
        )

    def contact_button_removed(self) -> bool:
        return any(isinstance(message.reply_markup, ReplyKeyboardRemove) for message in self.replies)

    def _message(self, **content: Any) -> Message:
        return Message(
            message_id=self._updates,
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=self.user,
            **content,
        )

    def _feed(self, **event: Any) -> str:
        self._updates += 1
        sent_before = len(self.telegram.requests)
        asyncio.run(self.dispatcher.feed_update(self.bot, Update(update_id=self._updates, **event)))
        self.replies = [
            request
            for request in self.telegram.requests[sent_before:]
            if isinstance(request, SendMessage)
        ]
        return self.reply


def agree(chat: BotChat) -> None:
    chat.send("/start")
    chat.press("Согласен")


def go_through_the_bot(chat: BotChat, club: str = "Покер-клуб «Обь»") -> None:
    """Goes through the whole sign-up: consent, the phone +7 913 555-12-34, the club."""
    agree(chat)
    chat.share_contact("+79135551234", first_name="Мария", last_name="Иванова")
    chat.press(club)
