from __future__ import annotations

import logging
from typing import Awaitable, Callable, List, Optional, Union, Type

from .fsm import State, StatesGroup, InvertedState
from .models import Update


class StopPropagation(Exception):
    pass


Handler = Callable[[object], Awaitable[None]]


class FieldFilter:
    def __init__(self, attr_name: str):
        self.attr_name = attr_name

    def __eq__(self, other):
        def _predicate(event) -> bool:
            return getattr(event, self.attr_name, None) == other
        return _predicate

    def __ne__(self, other):
        def _predicate(event) -> bool:
            return getattr(event, self.attr_name, None) != other
        return _predicate


class _FNamespace:
    text = FieldFilter("text")
    data = FieldFilter("data")


F = _FNamespace()


class Router:
    def __init__(self):
        self._message_handlers: List[Handler] = []
        self._callback_handlers: List[Handler] = []

    def _check_state_filter(self, state_filter, current_state: Optional[str]) -> bool:

        if state_filter is None:
            return True

        if isinstance(state_filter, InvertedState):
            return current_state != str(state_filter.state)

        if isinstance(state_filter, State):
            return current_state == str(state_filter)

        if isinstance(state_filter, type) and issubclass(state_filter, StatesGroup):
            prefix = f"{state_filter.__name__}:"
            return isinstance(current_state, str) and current_state.startswith(prefix)

        return False

    def message(
        self,
        *filters,
        state: Optional[Union[State, InvertedState, Type[StatesGroup]]] = None,
    ) -> Callable[[Handler], Handler]:

        def decorator(fn: Handler) -> Handler:
            async def wrapped(event, fsm_ctx):
                for flt in filters:
                    if callable(flt):
                        if not flt(event):
                            return
                    else:
                        return

                if state is not None:
                    current_state = await fsm_ctx.get_state()
                    if not self._check_state_filter(state, current_state):
                        return

                if fn.__code__.co_argcount == 2:
                    await fn(event, fsm_ctx)
                else:
                    await fn(event)

                raise StopPropagation

            self._message_handlers.append(wrapped)
            return fn

        return decorator

    def callback_query(
        self,
        *filters,
        state: Optional[Union[State, InvertedState, Type[StatesGroup]]] = None,
    ) -> Callable[[Handler], Handler]:

        def decorator(fn: Handler) -> Handler:
            async def wrapped(event, fsm_ctx):
                for flt in filters:
                    if callable(flt):
                        if not flt(event):
                            return
                    else:
                        return

                if state is not None:
                    current_state = await fsm_ctx.get_state()
                    if not self._check_state_filter(state, current_state):
                        return

                if fn.__code__.co_argcount == 2:
                    await fn(event, fsm_ctx)
                else:
                    await fn(event)

                raise StopPropagation

            self._callback_handlers.append(wrapped)
            return fn

        return decorator

    async def dispatch(self, update: Update, state):
        logging.debug(f"[Router.dispatch] update.type={update.type!r}, handlers={len(self._message_handlers)}")
        if update.type == "text" and update.message:
            for h in self._message_handlers:
                try:
                    await h(update.message, state)
                except StopPropagation:
                    raise

        elif update.type == "cb" and update.callback_query:
            for h in self._callback_handlers:
                try:
                    await h(update.callback_query, state)
                except StopPropagation:
                    raise