"""Обработчики Telegram: команды + свободный текст.

`cmd_<name>` автоматически регистрируется как команда `/<name>`; первая строка
docstring — описание в нативном меню Telegram. Каждый хендлер проходит проверку
доступа по whitelist из `Config`.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import logging
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from typing import Any

from google.genai import errors
from telegram import BotCommand, Chat, Message, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .assistant import Assistant
from .config import Config
from .modelpool import ModelPool
from .stats import Stats

log = logging.getLogger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]


class Commands:
    def __init__(
        self,
        config: Config,
        stats: Stats,
        pool: ModelPool,
        assistant_factory: Callable[[], Assistant],
    ) -> None:
        self._config = config
        self._stats = stats
        self._pool = pool
        self._new_assistant = assistant_factory

    # --- команды ---------------------------------------------------------------

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """приветствие и подсказка"""
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(
            "Ассистент Lumère — помощник по контенту в голосе бренда.\n\n"
            "Пришли задачу текстом: пост, описание продукта, ответ клиенту.\n"
            "/check — проверить последний ответ по Brand Voice\n"
            "/reset — очистить историю диалога"
        )

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """очистить историю диалога"""
        message = update.effective_message
        if message is None:
            return
        self._assistant(context).reset()
        await message.reply_text("История диалога очищена.")

    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """статистика запросов за сессию"""
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(f"{self._stats.render()}\nМодель: {self._pool.current}")

    async def cmd_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """проверить последний ответ по Brand Voice"""
        message = update.effective_message
        if message is None:
            return
        reply = await self._generate(message, self._assistant(context).check())
        if reply is not None:
            await message.reply_text(reply)

    # --- свободный текст ------------------------------------------------------

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.text is None:
            return
        reply = await self._generate(message, self._assistant(context).ask(message.text))
        if reply is not None:
            await message.reply_text(reply or "(пустой ответ)")

    # --- инфраструктура ------------------------------------------------------

    def _assistant(self, context: ContextTypes.DEFAULT_TYPE) -> Assistant:
        store = context.user_data
        assert store is not None  # всегда есть для апдейтов от пользователя
        assistant = store.get("assistant")
        if assistant is None:
            assistant = store["assistant"] = self._new_assistant()
        return assistant

    async def _generate(
        self, message: Message, coro: Coroutine[Any, Any, str]
    ) -> str | None:
        """Ждёт ответ модели (держа «печатает…»); при ошибке отвечает и возвращает None."""
        try:
            async with self._typing(message.chat):
                return await coro
        except errors.APIError as exc:
            log.warning("Gemini недоступен (%s): %s", getattr(exc, "code", "?"), exc)
            if getattr(exc, "code", None) == 429 and "PerDay" in str(exc):
                await message.reply_text(
                    "Все модели Gemini исчерпали дневной лимит — сбросится завтра "
                    "или смени ключ."
                )
            else:
                await message.reply_text("Gemini сейчас недоступен, попробуй через минуту.")
            return None
        except Exception:
            log.exception("Неожиданная ошибка при запросе к Gemini")
            await message.reply_text("Ошибка. Попробуй ещё раз.")
            return None

    @staticmethod
    @contextlib.asynccontextmanager
    async def _typing(chat: Chat) -> AsyncIterator[None]:
        """Держит индикатор «печатает…», пока идёт запрос (Telegram гасит его через ~5 с)."""

        async def loop() -> None:
            while True:
                with contextlib.suppress(Exception):
                    await chat.send_chat_action(ChatAction.TYPING)
                await asyncio.sleep(4)

        task = asyncio.create_task(loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _iter_commands(self) -> Iterator[tuple[str, Handler]]:
        for name, method in inspect.getmembers(self, inspect.iscoroutinefunction):
            if name.startswith("cmd_"):
                yield name.removeprefix("cmd_"), method

    @staticmethod
    def _describe(method: Handler) -> str:
        return (method.__doc__ or "").strip().split("\n", 1)[0]

    def _authorized(self, update: Update) -> bool:
        if not self._config.allowed_user_ids:
            return True
        user = update.effective_user
        return user is not None and user.id in self._config.allowed_user_ids

    def _guard(self, handler: Handler) -> Handler:
        """Оборачивает хендлер в проверку доступа."""

        @functools.wraps(handler)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            if not self._authorized(update):
                user_id = getattr(update.effective_user, "id", None)
                log.warning("Отказано в доступе: id=%s", user_id)
                if update.effective_message:
                    await update.effective_message.reply_text("Доступ запрещён.")
                return
            await handler(update, context)

        return wrapper

    async def post_init(self, app: Application) -> None:
        """Отдаёт список команд в нативное меню Telegram."""
        await app.bot.set_my_commands([
            BotCommand(command, self._describe(method) or command)
            for command, method in self._iter_commands()
        ])

    def register(self, app: Application) -> None:
        """Регистрирует команды и обработчик свободного текста с проверкой доступа."""
        for command, method in self._iter_commands():
            app.add_handler(CommandHandler(command, self._guard(method)))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._guard(self.on_message))
        )
