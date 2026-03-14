from __future__ import annotations
from typing import Dict, Any, Optional, Union, TYPE_CHECKING
from abc import ABC, abstractmethod
import json

if TYPE_CHECKING:
    # чтобы не тащить redis как жёсткую зависимость при импорте модуля
    from redis.asyncio import Redis


class BaseStorage(ABC):
    """
    Общий интерфейс для хранилищ (память, Redis, БД и т.д.).
    Аналогично aiogram.storage.*.
    """

    @abstractmethod
    async def get_data(self, chat_id: int) -> Dict[str, Any]:
        """
        Получить все данные по chat_id (включая __state__).
        Должен всегда возвращать словарь (возможно, пустой).
        """
        raise NotImplementedError

    @abstractmethod
    async def set_data(self, chat_id: int, data: Dict[str, Any]) -> None:
        """
        Полностью заменить данные по chat_id.
        """
        raise NotImplementedError

    @abstractmethod
    async def clear(self, chat_id: int) -> None:
        """
        Полностью удалить все данные по chat_id.
        """
        raise NotImplementedError


class MemoryStorage(BaseStorage):
    def __init__(self):
        self._data: Dict[int, Dict[str, Any]] = {}

    async def get_data(self, chat_id: int) -> Dict[str, Any]:
        # Всегда возвращаем один и тот же dict для chat_id
        return self._data.setdefault(chat_id, {})

    async def set_data(self, chat_id: int, data: Dict[str, Any]) -> None:
        # Полная замена (copy, чтобы не тащить внешний dict по ссылке)
        self._data[chat_id] = dict(data)

    async def clear(self, chat_id: int) -> None:
        self._data.pop(chat_id, None)


class RedisStorage(BaseStorage):
    """
    Упрощённое Redis‑хранилище, по аналогии с aiogram.storage.redis.

    Для каждого chat_id храним Hash в Redis:
        key = f"{prefix}:{chat_id}"
        field -> json.dumps(value)

    Требуется пакет `redis` (redis-py >= 4, модуль redis.asyncio).
    """

    def __init__(
        self,
        prefix: str,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        username: str = None,
        password: str = None,
        ):
        from redis.asyncio import Redis

        self._redis = Redis(host=host, port=port, db=db, username=username, password=password)
        self._prefix = prefix

    def _key(self, chat_id: int) -> str:
        return f"{self._prefix}:{chat_id}"

    async def get_data(self, chat_id: int) -> Dict[str, Any]:
        raw = await self._redis.hgetall(self._key(chat_id))
        if not raw:
            return {}

        result: Dict[str, Any] = {}
        for k, v in raw.items():
            # ключи/значения могут быть bytes
            if isinstance(k, (bytes, bytearray)):
                k = k.decode("utf-8", errors="ignore")
            if isinstance(v, (bytes, bytearray)):
                v = v.decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(v)
                # Нормализация: если кто-то сохранил строку "null" (а не JSON null),
                # превращаем её в None.
                if parsed == "null":
                    parsed = None
                result[k] = parsed
            except Exception:
                # если вдруг не JSON — вернём как есть
                result[k] = v
        return result

    async def set_data(self, chat_id: int, data: Dict[str, Any]) -> None:
        key = self._key(chat_id)

        if not data:
            # пустые данные — просто удаляем ключ
            await self._redis.delete(key)
            return

        mapping = {str(k): json.dumps(v) for k, v in data.items()}

        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.delete(key)
            await pipe.hset(key, mapping=mapping)
            await pipe.execute()

    async def clear(self, chat_id: int) -> None:
        await self._redis.delete(self._key(chat_id))


class InvertedState:
    """
    Обёртка для отрицания состояния: ~State.
    Используется только внутри Router.
    """

    def __init__(self, state: "State"):
        self.state = state


class State:
    """
    Аналог aiogram.types.State.
    При объявлении в StatesGroup получает строку вида 'GroupName:state_name'.
    """

    def __init__(self, state: Optional[str] = None):
        self.state: Optional[str] = state

    def __set_name__(self, owner: type, name: str):
        # Автоматически формируем имя стейта при объявлении в StatesGroup
        if self.state is None:
            self.state = f"{owner.__name__}:{name}"

    def __str__(self) -> str:
        # чтобы можно было делать str(MyGroup.state1)
        return self.state or ""

    def __invert__(self) -> InvertedState:
        """
        Позволяет писать: state=~MyStates.some_state
        (обработать любые состояния, КРОМЕ этого).
        """
        return InvertedState(self)


class StatesGroup:
    """
    Базовый класс для групп состояний, аналог aiogram.dispatcher.filters.state.StatesGroup.
    Просто служит родителем для классов с атрибутами типа State.
    """
    pass


class FSMContext:
    """
    Упрощённый аналог aiogram.dispatcher.FSMContext.

    В хранилище для каждого chat_id лежит обычный словарь:
        {
            "__state__": "MyGroup:some_state" | None,
            ...произвольные данные...
        }
    """

    STATE_KEY = "__state__"

    def __init__(self, storage: BaseStorage, chat_id: int):
        self.storage = storage
        self.chat_id = chat_id

    async def set_state(self, state: Optional[Union[State, str]]) -> None:
        """
        state: State или строка ('MyGroup:state'), или None для сброса состояния.
        """
        if isinstance(state, State):
            value = state.state
        else:
            value = state

        data = await self.storage.get_data(self.chat_id)
        data[self.STATE_KEY] = value
        await self.storage.set_data(self.chat_id, data)

    async def get_state(self) -> Optional[str]:
        data = await self.storage.get_data(self.chat_id)
        return data.get(self.STATE_KEY)

    async def update_data(
        self,
        data: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Логика:
        - если передан ТОЛЬКО словарь `data` (без kwargs) -> полная перезапись данных (с сохранением __state__);
        - если передана одна/несколько пар key=value (kwargs) -> точечное обновление/добавление этих ключей;
        - если переданы и data, и kwargs -> точечное обновление (kwargs перекрывают data).
        """
        stored = await self.storage.get_data(self.chat_id)

        # Полная замена, если пришёл именно словарь (даже пустой) и нет kwargs
        if data is not None and not kwargs:
            state_value = stored.get(self.STATE_KEY)
            new_stored: Dict[str, Any] = {}
            if state_value is not None:
                new_stored[self.STATE_KEY] = state_value
            new_stored.update(dict(data))  # copy, чтобы не держать внешнюю ссылку
            await self.storage.set_data(self.chat_id, new_stored)
            return new_stored

        # Иначе — частичное обновление (как раньше)
        if data:
            stored.update(data)

        if kwargs:
            stored.update(kwargs)

        await self.storage.set_data(self.chat_id, stored)
        return stored

    async def get_data(self) -> Dict[str, Any]:
        """
        Аналог FSMContext.get_data: возвращаем все данные, кроме ключа состояния.
        """
        data = await self.storage.get_data(self.chat_id)
        return {k: v for k, v in data.items() if k != self.STATE_KEY}

    async def clear(self) -> None:
        """
        Аналог FSMContext.clear: удаляем все данные и состояние для chat_id.
        """
        await self.storage.clear(self.chat_id)