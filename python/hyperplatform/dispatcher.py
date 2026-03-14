from __future__ import annotations
import asyncio
import logging
from typing import Dict, Optional
from .bot import Bot
from .router import Router, StopPropagation
from .models import Update
from .fsm import FSMContext


class Dispatcher:
    def __init__(self, *routers: Router, per_chat_concurrency: int = 1, poll_timeout: int = 30, poll_limit: int = 100):
        self.routers = list(routers)
        self.per_chat_concurrency = per_chat_concurrency
        self.poll_timeout = poll_timeout
        self.poll_limit = poll_limit

        self._chat_semaphores: Dict[int, asyncio.Semaphore] = {}
        self._stop = asyncio.Event()
        self._last_offset: Optional[int] = None

        self._fsm_context_cls = FSMContext

    def _sem_for_chat(self, chat_id: int) -> asyncio.Semaphore:
        sem = self._chat_semaphores.get(chat_id)
        if sem is None:
            sem = asyncio.Semaphore(self.per_chat_concurrency)
            self._chat_semaphores[chat_id] = sem
        return sem

    async def _handle_update(self, bot: Bot, upd: Update):
        if upd.message is not None:
            upd.message._bot = bot
        if upd.callback_query is not None and upd.callback_query.message is not None:
            upd.callback_query.message._bot = bot

        fsm_ctx = self._fsm_context_cls(bot.storage, upd.chat_id)

        sem = self._sem_for_chat(upd.chat_id)
        async with sem:
            for router in self.routers:
                try:
                    await router.dispatch(upd, fsm_ctx)
                except StopPropagation:
                    break

    async def start_polling(self, bot: Bot):
        logging.info("Polling started")
        logging.info(f"Routers registered: {len(self.routers)}")
        for r in self.routers:
            logging.info(
                f"  Router {r}: {len(r._message_handlers)} msg handlers, {len(r._callback_handlers)} cb handlers")
        while not self._stop.is_set():
            try:
                logging.debug("Calling get_updates...")
                updates = await bot.get_updates(
                    limit=self.poll_limit,
                    offset=self._last_offset,
                    timeout=self.poll_timeout,
                )
                logging.debug(f"get_updates returned {len(updates)} updates")
                if updates:
                    self._last_offset = max(u.id for u in updates)

                    tasks = [asyncio.create_task(self._handle_update(bot, u)) for u in updates]
                    if tasks:
                        await asyncio.gather(*tasks)
                else:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error while polling: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def stop(self):
        self._stop.set()