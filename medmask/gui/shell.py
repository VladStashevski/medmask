"""Утилиты интерфейса без Qt: открытие папки, склонения, время, вид документа.

Вынесены отдельно, чтобы их можно было проверять тестами без запуска окна.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Значок строки выбирается по расширению: пользователю важно с одного взгляда
# отличить скан от таблицы, а не знать точный формат.
_KIND_BY_SUFFIX = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".tif": "image",
    ".tiff": "image",
    ".bmp": "image",
    ".webp": "image",
    ".docx": "doc",
    ".rtf": "doc",
    ".odt": "doc",
    ".odg": "doc",
    ".xlsx": "sheet",
    ".xlsm": "sheet",
    ".txt": "text",
}


def open_folder(path: Path) -> None:
    """Показывает готовую папку средствами системы."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    elif os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def plural(count: int, one: str, few: str, many: str) -> str:
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        return many
    tail %= 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def format_duration(seconds: float) -> str:
    """Время работы в моноширинном виде: минуты не должны прыгать по ширине."""
    total = max(0, int(seconds))
    minutes, second = divmod(total, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours:d}:{minutes:02d}:{second:02d}"
    return f"{minutes:02d}:{second:02d}"


def kind_of(name: str) -> str:
    return _KIND_BY_SUFFIX.get(Path(name).suffix.lower(), "text")


def breadcrumb(path: Path, parts: int = 3) -> str:
    """Короткий путь под именем папки.

    Полный путь в окно шириной 760 не помещается и все равно читается плохо.
    Домашний каталог отбрасывается: он одинаков у всех строк и ничего не
    добавляет, а отброшенное начало помечается многоточием.
    """
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        home = None
    segments: list[str]
    if home is not None and path != home:
        try:
            segments = list(path.relative_to(home).parts)
        except ValueError:
            segments = [part for part in path.parts if part not in ("/", "\\")]
    else:
        segments = [part for part in path.parts if part not in ("/", "\\")]
    if not segments:
        return str(path)
    shown = segments[-parts:]
    prefix = "…  /  " if len(segments) > len(shown) else ""
    return prefix + "  /  ".join(shown)
