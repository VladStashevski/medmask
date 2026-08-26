"""Выбор интерфейса при запуске.

Основное окно — Qt Quick (medmask.gui). Прежнее окно на tkinter остается
запасным: оно не требует PySide6 и открывается по MEDMASK_UI=tk или когда
Qt в системе нет. Команда запуска и пакетный режим от этого не меняются.
"""

from __future__ import annotations

import os
import sys


def _report(message: str) -> None:
    """Печатает, если есть куда: в оконной сборке stdout отсутствует."""
    stream = sys.stderr
    if stream is None:
        return
    try:
        print(message, file=stream)
        stream.flush()
    except (ValueError, OSError):
        pass


def main() -> None:
    requested = os.environ.get("MEDMASK_UI", "").strip().lower()
    if requested in ("tk", "tkinter"):
        from .app import main as tk_main

        tk_main()
        return

    try:
        from .gui import main as qt_main
    except ImportError as error:
        if requested in ("qt", "qml"):
            raise
        _report(f"Интерфейс Qt недоступен ({error}), открываю запасное окно.")
        from .app import main as tk_main

        tk_main()
        return

    qt_main()
