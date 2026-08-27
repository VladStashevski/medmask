"""Собирает MedMask нативным компилятором Nuitka.

QML перед компиляцией превращается в модуль ресурсов Qt. Он входит в основной
исполняемый файл и удаляется из checkout сразу после сборки.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from compile_qml_resources import DEFAULT_OUTPUT, compile_resources


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
QML_UNUSED = (
    "Qt/labs",
    "Qt3D",
    "Qt5Compat",
    "QtCharts",
    "QtDataVisualization",
    "QtGraphs",
    "QtLocation",
    "QtMultimedia",
    "QtPositioning",
    "QtQuick/Pdf",
    "QtQuick/Particles",
    "QtQuick/Scene2D",
    "QtQuick/Scene3D",
    "QtQuick/Timeline",
    "QtQuick/VectorImage",
    "QtQuick/VirtualKeyboard",
    "QtQuick3D",
    "QtRemoteObjects",
    "QtScxml",
    "QtSensors",
    "QtTest",
    "QtTextToSpeech",
    "QtWebChannel",
    "QtWebEngine",
    "QtWebSockets",
    "QtWebView",
)
NATIVE_UNUSED_MODULES = (
    # Qt входит в нативную поставку, поэтому старый исходный fallback на Tk
    # только раздувает артефакт Tcl/Tk и служебными скриптами.
    "medmask.app",
    "medmask.theme",
    "medmask.ui",
    "tkinter",
    # MedMask всегда задаёт EngineType.ONNXRUNTIME. Остальные backends RapidOCR
    # ссылаются на тяжёлые необязательные фреймворки и в релизе недостижимы.
    "rapidocr.inference_engine.mnn",
    "rapidocr.inference_engine.openvino",
    "rapidocr.inference_engine.paddle",
    "rapidocr.inference_engine.pytorch",
    "rapidocr.inference_engine.tensorrt",
    "onnxruntime.transformers",
)
QT_DROP = (
    "webengine",
    "webview",
    "webchannel",
    "websockets",
    "quick3d",
    "qt3d",
    "multimedia",
    "spatialaudio",
    "texttospeech",
    "qtcharts",
    "datavisualization",
    "qtgraphs",
    "qtsensors",
    "qtpositioning",
    "qtlocation",
    "qtbluetooth",
    "qtnfc",
    "qtserialport",
    "qtserialbus",
    "qtremoteobjects",
    "qtscxml",
    "qtsql",
    "sqldrivers",
    "qttest",
    "qtdesigner",
    "qthelp",
    "qthttpserver",
    "qtpdf",
    "qpdf",
)


def _version() -> str:
    namespace: dict[str, str] = {}
    source = (ROOT / "medmask" / "__init__.py").read_text(encoding="utf-8")
    exec(compile(source, "medmask/__init__.py", "exec"), namespace)
    return namespace["__version__"]


def _data(source: str, target: str) -> str:
    return f"--include-data-files={ROOT / source}={target}"


def _remove_previous_output() -> None:
    DIST.mkdir(exist_ok=True)
    for target in (DIST / "MedMask.app", DIST / "MedMask.dist", DIST / "MedMask"):
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()


def _command() -> list[str]:
    version = _version()
    jobs = max(1, min(4, os.cpu_count() or 1))
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=app-dist",
        "--output-dir=dist",
        "--output-folder-name=MedMask",
        "--include-package=medmask",
        # RapidOCR exposes its entry point through module-level __getattr__.
        # Nuitka cannot discover that lazy import from static analysis alone.
        "--include-module=rapidocr.main",
        "--include-module=onnxruntime",
        "--include-package-data=rapidocr:config.yaml",
        "--include-package-data=rapidocr:default_models.yaml",
        "--include-module=medmask.gui._qml_resources",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=qml",
        "--noinclude-qt-translations",
        "--noinclude-data-files=**/*.o",
        "--noinclude-data-files=**/*.a",
        "--noinclude-data-files=**/*.prl",
        "--noinclude-dlls=**/*.o",
        "--noinclude-dlls=**/*.a",
        "--nofollow-import-to=*.tests",
        "--noinclude-setuptools-mode=nofollow",
        "--noinclude-pytest-mode=nofollow",
        "--noinclude-unittest-mode=nofollow",
        "--noinclude-pydoc-mode=nofollow",
        "--python-flag=no_asserts",
        "--python-flag=no_docstrings",
        "--python-flag=isolated",
        "--python-flag=safe_path",
        "--deployment",
        # ProcessPool's spawn protocol is not portable across the protected
        # GUI launchers. The source build remains parallel; the native release
        # uses the deterministic in-process path.
        "--force-runtime-environment-variable=MEDMASK_DISABLE_PARALLEL=1",
        f"--lto={os.environ.get('MEDMASK_LTO', 'yes')}",
        "--reproducible=yes",
        f"--jobs={jobs}",
        "--remove-output",
        "--progress-bar=none",
        "--assume-yes-for-downloads",
        "--report=build/nuitka-report.xml",
        "--report-diffable",
        "--product-name=MedMask",
        f"--product-version={version}",
        f"--file-version={version}",
        _data("medmask/assets/*.onnx", "medmask/assets/"),
        _data(
            "medmask/assets/LiberationSans-Regular.ttf",
            "medmask/assets/LiberationSans-Regular.ttf",
        ),
        _data("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    ]
    if sys.platform == "darwin":
        command.extend(
            [
                "--clang",
                "--output-filename=MedMaskCore",
                "--macos-app-name=MedMask",
                f"--macos-app-version={version}",
                "--macos-app-mode=gui",
                "--macos-signed-app-name=ru.medmask.local",
                "--macos-prohibit-multiple-instances",
                f"--macos-app-icon={ROOT / 'medmask/assets/app_icon.icns'}",
            ]
        )
    elif sys.platform == "win32":
        command.extend(
            [
                "--msvc=latest",
                "--output-filename=MedMask",
                "--windows-console-mode=disable",
                "--file-description=Локальное обезличивание медицинских документов",
                f"--windows-icon-from-ico={ROOT / 'medmask/assets/app_icon.ico'}",
            ]
        )
    else:
        raise RuntimeError("Защищённая сборка настроена только для macOS и Windows.")
    for qml_module in QML_UNUSED:
        pattern = f"PySide6/qml/{qml_module}/**"
        command.extend(
            [
                f"--noinclude-data-files={pattern}",
                f"--noinclude-dlls={pattern}",
            ]
        )
    for module in NATIVE_UNUSED_MODULES:
        command.append(f"--nofollow-import-to={module}")
    command.append("main.py")
    return command


def _normalize_output() -> tuple[Path, Path]:
    if sys.platform == "darwin":
        bundle = DIST / "MedMask.app"
        executable = bundle / "Contents" / "MacOS" / "MedMaskCore"
    else:
        bundle = DIST / "MedMask"
        executable = bundle / "MedMask.exe"
    if not executable.is_file():
        raise RuntimeError(f"Nuitka не создал ожидаемый файл: {executable}")
    return bundle, executable


def _is_unused_qt(path: Path) -> bool:
    # Windows называет библиотеки Qt6Foo, macOS — QtFoo. Нормализация делает
    # список исключений единым для двух платформ.
    probe = path.as_posix().lower().replace("qt6", "qt")
    return any(marker in probe for marker in QT_DROP)


def _remove_unused_qt(bundle: Path) -> None:
    # Плагин Nuitka сначала находит зависимости всех QML-модулей Qt, а фильтры
    # QML применяет позднее. Поэтому библиотеки WebEngine/3D/PDF могут остаться
    # без потребителей. Удаляем только семейства, отсутствующие в импортах UI.
    for path in sorted(bundle.rglob("*"), key=lambda item: len(item.parts)):
        if not path.exists() or not _is_unused_qt(path.relative_to(bundle)):
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def _remove_service_files(bundle: Path, executable: Path) -> None:
    directory_names = {"__pycache__", ".pytest_cache"}
    directory_suffixes = (".dSYM", ".dist-info", ".egg-info")
    file_suffixes = (
        ".py",
        ".pyc",
        ".pyo",
        ".pyi",
        ".pdb",
        ".map",
        ".qmltypes",
        ".qrc",
        ".o",
        ".a",
        ".prl",
    )
    for path in sorted(bundle.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and (
            path.name in directory_names or path.name.endswith(directory_suffixes)
        ):
            shutil.rmtree(path)
        elif path.is_file() and path.name.endswith(file_suffixes):
            path.unlink()

    # Nuitka уже выпускает stripped-бинарник; второй проход удаляет оставшиеся
    # локальные символы после упаковки приложения. Подпись ставится позднее.
    if sys.platform == "darwin":
        subprocess.run(["strip", "-x", str(executable)], check=True)


def main() -> int:
    _remove_previous_output()
    BUILD.mkdir(exist_ok=True)
    compile_resources()
    try:
        subprocess.run(_command(), cwd=ROOT, check=True)
    finally:
        DEFAULT_OUTPUT.unlink(missing_ok=True)
    bundle, executable = _normalize_output()
    _remove_unused_qt(bundle)
    _remove_service_files(bundle, executable)
    print(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
