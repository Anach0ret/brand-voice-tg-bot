"""Список моделей Gemini с фолбэком.

Если текущая модель упёрлась в дневной лимит (429 PerDay) или исчезла (404) —
переходим к следующей. Общий на весь процесс: дневная квота — на проект, не на
пользователя. Только вперёд; при рестарте бота список начинается сначала.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class ModelPool:
    def __init__(self, models: list[str]) -> None:
        if not models:
            raise ValueError("список моделей пуст")
        self._models = models
        self._idx = 0

    @property
    def current(self) -> str:
        return self._models[self._idx]

    def advance(self) -> str | None:
        """Перейти к следующей модели. Возвращает её имя или None, если больше нет."""
        if self._idx + 1 >= len(self._models):
            return None
        self._idx += 1
        log.warning("Переключился на модель %s", self.current)
        return self.current
