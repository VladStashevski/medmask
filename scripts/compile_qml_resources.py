"""Компилирует QML MedMask в сжатый модуль ресурсов Qt.

Получившийся ``_qml_resources.py`` — промежуточный файл. Nuitka превращает
его массив байтов в нативный бинарник, после чего сборщик удаляет модуль.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
QRC = ROOT / "medmask" / "gui" / "qml.qrc"
DEFAULT_OUTPUT = ROOT / "medmask" / "gui" / "_qml_resources.py"


def _rcc_executable() -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    # resolve() у venv приводит к системному Python и теряет каталог bin/Scripts.
    beside_python = Path(sys.executable).with_name(f"pyside6-rcc{suffix}")
    if beside_python.is_file():
        return beside_python
    discovered = shutil.which("pyside6-rcc")
    if discovered:
        return Path(discovered)
    raise RuntimeError("Не найден pyside6-rcc из установленного PySide6.")


def compile_resources(output: Path = DEFAULT_OUTPUT) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="medmask-qrc-") as temporary:
        generated = Path(temporary) / output.name
        subprocess.run(
            [
                str(_rcc_executable()),
                str(QRC),
                "--compress-algo",
                "zlib",
                "--compress",
                "9",
                "--threshold",
                "0",
                "-o",
                str(generated),
            ],
            cwd=ROOT,
            check=True,
        )
        generated.replace(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    print(compile_resources(arguments.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
