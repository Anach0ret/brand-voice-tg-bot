"""brand-voice-tg-bot — точка входа: сборка зависимостей и запуск."""

from __future__ import annotations

import logging

from google import genai
from telegram.ext import Application

from brand_voice_tg_bot.assistant import Assistant
from brand_voice_tg_bot.config import Config
from brand_voice_tg_bot.handlers import Commands
from brand_voice_tg_bot.modelpool import ModelPool
from brand_voice_tg_bot.prompts import Prompts
from brand_voice_tg_bot.stats import Stats


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)  # прячем INFO про AFC

    config = Config.from_env()
    prompts = Prompts.load()
    client = genai.Client(api_key=config.gemini_api_key)
    stats = Stats()
    pool = ModelPool(list(config.gemini_models))

    commands = Commands(
        config,
        stats,
        pool,
        assistant_factory=lambda: Assistant(
            client, pool, prompts.system, prompts.checklist, stats
        ),
    )

    app = (
        Application.builder()
        .token(config.bot_token)
        .post_init(commands.post_init)
        .build()
    )
    commands.register(app)

    log = logging.getLogger(__name__)
    log.info("Бот запущен (long polling). Модели: %s", ", ".join(config.gemini_models))
    app.run_polling()
