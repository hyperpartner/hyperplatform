from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

import json
from pydantic import BaseModel, RootModel

from .forms import FormData, FormSubmission

MessageType = Literal["text"]
UpdateType = Literal["text", "cb"]


class InlineButton(BaseModel):
    text: str
    callback_data: str
    align: Literal['left', 'center', 'right'] = 'center'


class InlineKeyboardMarkup(RootModel[List[List[InlineButton]]]):
    """Список инлайн‑кнопок (inline_keyboard)."""


class KeyboardButton(BaseModel):
    text: str


class Keyboard(RootModel[List[List[KeyboardButton]]]):
    """Список обычных кнопок (reply_keyboard)."""


class MessageAttachment(BaseModel):
    file_name: str
    file_path: str
    mime_type: str
    preview_path: Optional[str] = None



class ServerMessageBody(BaseModel):
    text: Optional[str] = None
    form_data: Optional[FormData] = None
    message_type: Literal["text", "callback", "document", "image", "audio", "form"]

    # опциональные поля ДОЛЖНЫ иметь default=None, иначе Pydantic требует их в JSON
    callback_message_id: Optional[int] = None
    copy_enabled: Optional[bool] = None
    new_line_html: bool = False
    notification: Optional[bool] = None
    inline_keyboard: Optional[InlineKeyboardMarkup] = None
    keyboard: Optional[Keyboard] = None
    attachment: Optional[MessageAttachment] = None


class ServerMessage(BaseModel):
    """
    Сырая серверная модель сообщения (как приходит в JSON'е).
    Оставлена для совместимости, если где-то понадобится работать
    с «чистыми» данными без helper‑методов.
    """

    chat_id: int
    is_from_bot: Optional[bool] = None
    message_id: Optional[int] = None
    body: Optional[ServerMessageBody] = None
    sent: Optional[datetime] = None
    user_email: Optional[str] = None


class ServerCallback(BaseModel):
    """
    Сырая серверная модель callback‑а.
    """

    data: str
    message: ServerMessage
    callback_message: ServerMessage


class Message(BaseModel):
    """Сообщение, с которым работают хендлеры."""

    chat_id: int
    is_from_bot: Optional[bool]
    message_id: Optional[int]
    body: Optional[ServerMessageBody]
    sent: Optional[datetime] = None
    user_email: Optional[str] = None

    class Config:
        # Позволяем навесить _bot из Dispatcher
        extra = "allow"

    @property
    def bot(self):
        bot = getattr(self, "_bot", None)
        if bot is None:
            raise RuntimeError("Bot is not attached to Message (_bot is missing)")
        return bot

    @property
    def text(self) -> Optional[str]:
        return self.body.text if self.body is not None else None

    async def edit(
            self,
            text: Optional[str] = None,
            inline_keyboard: Optional[InlineKeyboardMarkup] = None,
            message_type: str = "text",
    ):
        bot = getattr(self, "_bot", None)
        if bot is None:
            raise RuntimeError("Bot is not attached to Message (_bot is missing)")

        if self.message_id is None:
            raise RuntimeError("message_id is not set, cannot edit message")

        return await bot.edit_message(
            chat_id=self.chat_id,
            message_id=self.message_id,
            text=text or (self.text or ""),
            inline_keyboard=inline_keyboard,
        )

    async def delete(self):
        """
        Удаляет текущее сообщение через Bot.delete_message.
        """
        bot = getattr(self, "_bot", None)
        if bot is None:
            raise RuntimeError("Bot is not attached to Message (_bot is missing)")

        if self.message_id is None:
            raise RuntimeError("message_id is not set, cannot delete message")

        return await bot.delete_message(message_id=self.message_id)


    async def answer(
            self,
            text: Optional[str] = None,
            inline_keyboard: Optional[InlineKeyboardMarkup] = None,
            message_type: str = "text",
    ):
        bot = getattr(self, "_bot", None)
        if bot is None:
            raise RuntimeError("Bot is not attached to Message (_bot is missing)")

        return await bot.send_message(
            chat_id=self.chat_id,
            message_type=message_type,
            text=text or "",
            inline_keyboard=inline_keyboard,
        )


class CallbackQuery(BaseModel):
    """Callback‑запрос, с которым работают хендлеры."""

    data: str
    form_data: Optional[Dict[str, Any]] = None
    message: Message
    callback_message: Message

    class Config:
        extra = "allow"

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)

        if (
            self.message.body is not None
            and self.message.body.message_type == "form"
            and self.form_data is None
        ):
            try:
                parsed = json.loads(self.data)
                values = parsed.get("values")
                if isinstance(values, dict):
                    object.__setattr__(self, "form_data", values)
            except (json.JSONDecodeError, TypeError):
                pass


class Update(BaseModel):
    """
    Высокоуровневый апдейт, с которым работают Dispatcher и Router.

    Ожидаем, что сервер отдаёт структуру вида:
      {
        "update_id": ...,
        "message": { ... }?    # опционально
        "callback": {          # опционально
            "data": "...",
            "message": { ... },
            "callback_message": { ... }
        }
      }
    где message/callback_message имеют структуру ServerMessage.
    Pydantic сам приведёт их к Message/CallbackQuery.
    """

    update_id: int
    message: Optional[Message] = None
    callback: Optional[CallbackQuery] = None
    user_email: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)

        if self.user_email is None:
            return

        if self.message is not None and self.message.user_email is None:
            self.message.user_email = self.user_email

        if self.callback is not None:
            if self.callback.message is not None and self.callback.message.user_email is None:
                self.callback.message.user_email = self.user_email
            if (
                self.callback.callback_message is not None
                and self.callback.callback_message.user_email is None
            ):
                self.callback.callback_message.user_email = self.user_email

    @property
    def id(self) -> int:
        return self.update_id

    @property
    def callback_query(self) -> Optional[CallbackQuery]:
        return self.callback

    @property
    def chat_id(self) -> int:
        if self.message is not None:
            return self.message.chat_id
        if self.callback_query is not None:
            return self.callback_query.message.chat_id
        raise RuntimeError(
            "Update has neither message nor callback_query, chat_id is undefined"
        )

    @property
    def type(self) -> str:
        if self.message is not None:
            return "text"
        if self.callback_query is not None:
            return "cb"
        return "unknown"


def parse_update(update: Union[Dict[str, Any], Update]) -> Update:
    """
    Преобразует сырой апдейт (dict из JSON) в модель Update,
    либо просто возвращает уже готовый Update.
    """
    if isinstance(update, Update):
        return update

    return Update.model_validate(update)
