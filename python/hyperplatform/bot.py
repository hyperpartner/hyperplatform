from __future__ import annotations

import json

import aiohttp
from typing import Any, Dict, List, Optional, Literal

from .forms import FormData
from .models import Update, parse_update, ServerMessage, ServerMessageBody, Message
from .errors import ApiError
from .keyboard import InlineKeyboardMarkup
from .fsm import MemoryStorage, BaseStorage


class Bot:
    def __init__(
        self,
        base_url: str,
        token: str,
        session: Optional[aiohttp.ClientSession] = None,
        storage: Optional[BaseStorage] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session = session
        self._owns_session = session is None

        self.storage: BaseStorage = storage or MemoryStorage()

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self):
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def get_updates(self, limit: int = 100, offset: Optional[int] = None, timeout: Optional[int] = None) -> List[Update]:
        params: Dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset + 1
        if timeout is not None:
            params["timeout"] = timeout

        session = await self._get_session()
        url = f"{self.base_url}/getUpdates"
        async with session.get(url, headers=self.headers, params=params) as resp:
            data = await resp.json(content_type=None)

            if isinstance(data, list):
                raw_updates = data
            else:
                if not data.get("ok", True):
                    raise ApiError(str(data))
                raw_updates = data.get("updates", [])

            return [parse_update(u) for u in raw_updates]

    async def send_message(
            self,
            chat_id: int,
            text: str,
            message_type: Literal["text"] = "text",
            inline_keyboard: Optional[list] = None,
    ) -> int:
        if isinstance(inline_keyboard, InlineKeyboardMarkup):
            inline_keyboard = inline_keyboard.to_list()

        body = ServerMessageBody(
            message_type=message_type,
            text=text,
            inline_keyboard=inline_keyboard,
        )
        message = ServerMessage(chat_id=chat_id, body=body, is_from_bot=True)
        payload = message.model_dump(exclude_none=True)

        session = await self._get_session()
        url = f"{self.base_url}/sendMessage"
        async with session.post(url, headers=self.headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            return int(data["message_id"])


    async def send_form(
            self,
            chat_id: int,
            form: FormData,
            inline_keyboard: Optional[list] = None,
    ) -> int:
        if isinstance(inline_keyboard, InlineKeyboardMarkup):
            inline_keyboard = inline_keyboard.to_list()

        body = ServerMessageBody(
            message_type='form',
            form_data=form,
            inline_keyboard=inline_keyboard,
        )
        message = ServerMessage(chat_id=chat_id, body=body, is_from_bot=True)
        payload = message.model_dump(exclude_none=True)

        session = await self._get_session()
        url = f"{self.base_url}/sendMessage"
        async with session.post(url, headers=self.headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            return int(data["message_id"])




    async def edit_message(
            self,
            chat_id: int,
            message_id: int,
            text: str,
            inline_keyboard: Optional[list] = None,
    ) -> int:
        if isinstance(inline_keyboard, InlineKeyboardMarkup):
            inline_keyboard = inline_keyboard.to_list()

        body = ServerMessageBody(
            text=text,
            message_type="text",
            inline_keyboard=inline_keyboard,
        )
        message = ServerMessage(
            chat_id=chat_id,
            message_id=message_id,
            body=body,
            is_from_bot=True,
        )
        payload = message.model_dump(exclude_none=True)

        session = await self._get_session()
        url = f"{self.base_url}/editMessage"
        async with session.post(url, headers=self.headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 200:
                return int(data["message_id"])
            else:
                raise ApiError(str(resp))


    async def delete_message(
            self,
            message_id: int,
    ) -> Dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}/deleteMessage"
        payload: Dict[str, Any] = {"message_id": message_id}
        async with session.post(url, headers=self.headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            return data


    async def clear_chat(
            self,
            chat_id: int,
    ) -> Dict[str, Any]:

        session = await self._get_session()
        url = f"{self.base_url}/clearChat"
        payload: Dict[str, Any] = {"chat_id": chat_id}
        async with session.post(url, headers=self.headers, json=payload) as resp:
            data = await resp.json(content_type=None)
            return data




    async def get_file(self, file_path: str) -> bytes:
        session = await self._get_session()
        url = f"{self.base_url}/getFile/{file_path.lstrip('/')}"

        async with session.get(url, headers=self.headers) as resp:
            resp.raise_for_status()
            return await resp.read()


    async def send_file(
            self,
            chat_id: int,
            file: bytes,
            file_name: str,
            mime_type: str = None,
            text: str = "",
            chunk_size: int = 5 * 1024 * 1024,  # 5 MB
            inline_keyboard: Optional[list] = None,
    ) -> int:
        if isinstance(inline_keyboard, InlineKeyboardMarkup):
            inline_keyboard = inline_keyboard.to_list()

        session = await self._get_session()
        url = f"{self.base_url}/sendFile"
        total_size = len(file)

        if total_size <= chunk_size:
            form = aiohttp.FormData()
            form.add_field("chat_id", str(chat_id))
            form.add_field("text", text)
            form.add_field("file", file, filename=file_name, content_type=mime_type)
            form.add_field("mime_type", mime_type or "application/octet-stream")
            if inline_keyboard is not None:
                form.add_field("inline_keyboard", json.dumps(inline_keyboard))
            async with session.post(url, headers=self.headers, data=form) as resp:
                data = await resp.json(content_type=None)
                return int(data["message_id"])

        total_chunks = (total_size + chunk_size - 1) // chunk_size
        message_id = None

        for chunk_index in range(total_chunks):
            start = chunk_index * chunk_size
            chunk_data = file[start: start + chunk_size]

            form = aiohttp.FormData()
            form.add_field("chat_id", str(chat_id))
            form.add_field("text", text if chunk_index == 0 else "")
            form.add_field("file", chunk_data, filename=file_name, content_type=mime_type)
            form.add_field("chunk_index", str(chunk_index))
            form.add_field("total_chunks", str(total_chunks))
            form.add_field("chunk_size", str(chunk_size))
            form.add_field("total_size", str(total_size))
            form.add_field("mime_type", mime_type)
            form.add_field("file_name", file_name)
            if inline_keyboard is not None and chunk_index == 0:
                form.add_field("inline_keyboard", json.dumps(inline_keyboard))

            async with session.post(url, headers=self.headers, data=form) as resp:
                data = await resp.json(content_type=None)
                if chunk_index == 0:
                    message_id = int(data["message_id"])

        return message_id
