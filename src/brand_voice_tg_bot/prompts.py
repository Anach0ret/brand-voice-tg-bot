"""Загрузка текстов промптов из каталога `prompts/` в корне репозитория.

`system_prompt.md` / `checklist.md` — рабочие версии под конкретный бренд (в .gitignore).
Если их нет, берётся `*.example.md` из репозитория (с предупреждением в лог).
Держатся отдельно от кода, чтобы их правил не-разработчик.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _read(directory: Path, name: str) -> str:
    real = directory / f"{name}.md"
    if real.is_file():
        return real.read_text(encoding="utf-8")
    example = directory / f"{name}.example.md"
    if example.is_file():
        log.warning(
            "%s.md не найден — использую %s. Скопируй и заполни под свой бренд.",
            name, example.name,
        )
        return example.read_text(encoding="utf-8")
    raise RuntimeError(f"нет ни {real.name}, ни {example.name} в {directory}")


@dataclass(frozen=True)
class Prompts:
    system: str
    checklist: str

    @classmethod
    def load(cls, directory: Path = _PROMPTS_DIR) -> "Prompts":
        if not directory.is_dir():
            raise RuntimeError(f"каталог с промптами не найден: {directory}")
        return cls(
            system=_read(directory, "system_prompt"),
            checklist=_read(directory, "checklist"),
        )
