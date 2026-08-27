"""Проверяет, что релиз нативный и не содержит исходники MedMask."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SOURCE_SUFFIXES = {".py", ".pyc", ".pyo", ".pyi", ".qrc"}
SERVICE_SUFFIXES = {".pdb", ".map", ".qmltypes", ".o", ".a", ".prl"}
RAW_SOURCE_MARKERS = (
    b"from medmask.launcher import main",
    b"def process_folder(",
    b"import QtQuick",
)


def verify(bundle: Path, executable: Path) -> None:
    if not bundle.is_dir() or not executable.is_file():
        raise RuntimeError("Не найден собранный MedMask.")

    forbidden = [
        path.relative_to(bundle)
        for path in bundle.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SOURCE_SUFFIXES | SERVICE_SUFFIXES
    ]
    forbidden.extend(
        path.relative_to(bundle)
        for path in bundle.rglob("*")
        if path.is_dir() and path.name.endswith((".dSYM", ".dist-info", ".egg-info"))
    )
    own_qml = [
        path.relative_to(bundle)
        for path in bundle.rglob("*.qml")
        if "medmask/gui/qml" in path.as_posix().lower()
    ]
    if forbidden or own_qml:
        details = ", ".join(map(str, [*forbidden, *own_qml][:20]))
        raise RuntimeError(f"В защищённой сборке остались исходники/метаданные: {details}")

    executable_bytes = executable.read_bytes()
    exposed = [marker.decode("ascii") for marker in RAW_SOURCE_MARKERS if marker in executable_bytes]
    if exposed:
        raise RuntimeError(
            "В исполняемом файле обнаружен несжатый исходный текст: "
            + ", ".join(exposed)
        )

    if sys.platform == "darwin":
        kind = subprocess.run(
            ["file", str(executable)], capture_output=True, text=True, check=True
        ).stdout
        if "Mach-O" not in kind:
            raise RuntimeError("Главный файл не является нативным Mach-O.")
        subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True
        )
    elif sys.platform == "win32" and executable.suffix.lower() != ".exe":
        raise RuntimeError("Главный файл не является Windows executable.")

    print("защищённая сборка: исходников и отладочных файлов нет")


def main() -> int:
    if len(sys.argv) != 3:
        print("Запуск: verify_protected_build.py <bundle> <executable>", file=sys.stderr)
        return 2
    verify(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
