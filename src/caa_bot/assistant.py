"""Диалог с Gemini для одного пользователя Telegram.

История живёт в chat-сессии SDK (в памяти процесса — при рестарте бота теряется,
это осознанно: без БД). Модель берётся из общего `ModelPool` с фолбэком.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from google import genai
from google.genai import errors, types

from .modelpool import ModelPool
from .stats import Stats

log = logging.getLogger(__name__)

_TRANSIENT_CODES = (429, 500, 503)  # rate limit / server error / перегрузка
_RETRIES = 2

_T = TypeVar("_T")


class Assistant:
    def __init__(
        self,
        client: genai.Client,
        pool: ModelPool,
        system_prompt: str,
        checklist: str,
        stats: Stats,
    ) -> None:
        self._client = client
        self._pool = pool
        self._checklist = checklist
        self._stats = stats
        self._config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            # инструментов нет — отключаем function calling (и его INFO-логи)
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self._chat: "genai.chats.AsyncChat | None" = None
        self._chat_model = ""

    def reset(self) -> None:
        """Очистить историю диалога."""
        self._chat = None

    async def ask(self, text: str) -> str:
        response = await self._gen(lambda: self._ensure_chat().send_message(text))
        return (response.text or "").strip()

    async def check(self) -> str:
        """Оценить последний ответ ассистента по чек-листу бренда (вне истории)."""
        last = self._last_model_text()
        if not last:
            return "Нечего проверять — ассистент ещё не отвечал."

        prompt = (
            "Ты — редактор бренда. Оцени ТЕКСТ по ЧЕК-ЛИСТУ.\n"
            "Формат ответа: первая строка — вердикт "
            "(соответствует / частично / не соответствует); "
            "далее — список нарушений с цитатами. Текст не переписывай.\n\n"
            f"ЧЕК-ЛИСТ:\n{self._checklist}\n\n"
            f"ТЕКСТ:\n{last}"
        )
        response = await self._gen(
            lambda: self._client.aio.models.generate_content(
                model=self._pool.current, contents=prompt, config=self._config
            )
        )
        return (response.text or "").strip()

    async def _gen(self, factory: Callable[[], Awaitable[_T]]) -> _T:
        """Запрос к Gemini: ретрай на 429/500/503, фолбэк на след. модель при
        дневном лимите (429 PerDay) или пропаже модели (404), учёт в статистике."""
        self._stats.requests += 1
        tries_on_model = 0
        delay = 2.0
        while True:
            try:
                result = await factory()
            except errors.APIError as exc:
                code = getattr(exc, "code", None)
                switch = code == 404 or (code == 429 and "PerDay" in str(exc))
                if switch:
                    if self._pool.advance() is None:
                        self._stats.failed += 1
                        log.warning("Gemini: все модели недоступны (последняя — %s)", code)
                        raise
                    tries_on_model = 0
                    delay = 2.0
                    continue  # _ensure_chat пересоздаст сессию под новую модель, сохранив историю
                if code in _TRANSIENT_CODES and tries_on_model < _RETRIES:
                    tries_on_model += 1
                    self._stats.retries += 1
                    log.warning(
                        "Gemini %s — повтор %d/%d через %.0f с",
                        code, tries_on_model, _RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                self._stats.failed += 1
                log.warning("Gemini %s — все попытки исчерпаны", code)
                raise
            except Exception:
                self._stats.failed += 1
                raise
            else:
                self._stats.ok += 1
                if tries_on_model:
                    log.info("Gemini — успех после %d повтор(ов)", tries_on_model)
                return result

    def _ensure_chat(self) -> "genai.chats.AsyncChat":
        if self._chat is None or self._chat_model != self._pool.current:
            # смена модели — переносим историю (только завершённые ходы, без
            # упавшего запроса); после reset() истории нет
            history = self._chat.get_history(curated=True) if self._chat else None
            self._chat_model = self._pool.current
            self._chat = self._client.aio.chats.create(
                model=self._chat_model, config=self._config, history=history or None
            )
        return self._chat

    def _last_model_text(self) -> str:
        """Текст последнего ответа модели из истории диалога."""
        history = self._chat.get_history(curated=True) if self._chat else []
        for content in reversed(list(history)):
            if getattr(content, "role", None) != "model":
                continue
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "text", None):
                    return part.text
        return ""
