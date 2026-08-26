"""Окно MedMask на PySide6 и Qt Quick.

Пакет отвечает только за внешний вид и связь с движком: обработку документов
целиком выполняет medmask.batch, здесь он не дублируется.
"""

from __future__ import annotations

__all__ = ["main"]


def main() -> None:
    from .application import main as _main

    _main()
