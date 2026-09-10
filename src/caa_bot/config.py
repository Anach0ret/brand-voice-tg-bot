"""Конфигурация бота из окружения (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_MODELS = (
    # порядок = приоритет; каждая следующая — резерв при 429 (дневной лимит) / 404
    "gemini-3.5-flash-lite, gemini-3.1-flash-lite, "  # lite: ~1000 запросов/сутки каждая, быстрые
    "gemini-3.6-flash, gemini-3.5-flash, "  # full flash: 20/сутки, точнее держат длинный промпт
    "gemini-3.7-flash, gemini-3.8-flash, gemini-3-flash-preview"  # последний резерв
)


@dataclass(frozen=True)
class Config:
    bot_token: str
    gemini_api_key: str
    gemini_models: tuple[str, ...]  # по порядку, с фолбэком
    allowed_user_ids: frozenset[int]  # пусто — бот отвечает всем

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "").strip()
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not token or not key:
            raise RuntimeError(
                "BOT_TOKEN или GEMINI_API_KEY не задан — заполни .env (см. .env.example)"
            )

        raw_models = os.getenv("GEMINI_MODEL", _DEFAULT_MODELS)
        models = tuple(m.strip() for m in raw_models.split(",") if m.strip())

        raw_ids = os.getenv("ALLOWED_USER_IDS", "")
        return cls(
            bot_token=token,
            gemini_api_key=key,
            gemini_models=models or ("gemini-3.5-flash-lite",),
            allowed_user_ids=frozenset(
                int(x) for x in raw_ids.replace(" ", "").split(",") if x
            ),
        )
