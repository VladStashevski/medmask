"""Единая предрелизная проверка без смешивания Tk и Qt в одном процессе."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKS = (
    ("Статический анализ", [sys.executable, "-m", "ruff", "check", "."]),
    (
        "Движок, приватность и упаковка",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "--ignore=tests/test_ui.py",
            "--ignore=tests/test_gui.py",
        ],
    ),
    # Компактный progress/capture pytest 9 конфликтует с нативным Tk на macOS 26.
    # Подробный режим без capture обходит системный deadlock и сохраняет имена тестов.
    (
        "Запасной Tk-интерфейс",
        [sys.executable, "-m", "pytest", "-vv", "-s", "tests/test_ui.py"],
    ),
    ("Основной Qt-интерфейс", [sys.executable, "-m", "pytest", "tests/test_gui.py"]),
)


def main() -> int:
    for label, command in CHECKS:
        print(f"\n=== {label} ===", flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
