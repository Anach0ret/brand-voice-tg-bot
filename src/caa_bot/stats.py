"""Счётчики запросов за сессию (в памяти, сбрасываются при рестарте)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Stats:
    started: float = field(default_factory=time.monotonic)
    requests: int = 0  # запросов к Gemini (обычные ответы + /check)
    ok: int = 0
    failed: int = 0
    retries: int = 0  # сколько раз сработал повтор на 429/503

    def render(self) -> str:
        up = int(time.monotonic() - self.started)
        h, rem = divmod(up, 3600)
        m, s = divmod(rem, 60)
        uptime = f"{h} ч {m} мин" if h else f"{m} мин {s} с"
        return (
            f"Аптайм: {uptime}\n"
            f"Запросов к Gemini: {self.requests}\n"
            f"  успешно: {self.ok}\n"
            f"  ошибок: {self.failed}\n"
            f"  повторов (429/503): {self.retries}"
        )
