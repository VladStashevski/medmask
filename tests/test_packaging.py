"""Проверки поставки: встроенные ресурсы и единственная версия."""

from __future__ import annotations

import hashlib
import io
import re
import runpy
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QResource

from medmask import __version__
from medmask import depersonalizer as engine

ROOT = Path(__file__).resolve().parent.parent
FONT_SHA256 = "76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8"


def test_font_is_bundled_with_the_package() -> None:
    assert engine.BUNDLED_FONT_PATH.is_file()
    digest = hashlib.sha256(engine.BUNDLED_FONT_PATH.read_bytes()).hexdigest()
    assert digest == FONT_SHA256


def test_engine_prefers_the_bundled_font() -> None:
    """PDF не должен зависеть от того, какие шрифты стоят в системе."""
    assert engine._find_cyrillic_font() == str(engine.BUNDLED_FONT_PATH)


def test_font_license_is_documented() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Liberation" in notices
    assert "SIL Open Font License" in notices
    assert FONT_SHA256 in notices


def test_pymupdf_dual_license_is_documented() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    normalized = " ".join(notices.split())
    assert "PyMuPDF" in notices
    assert "GNU Affero General Public License" in normalized
    assert "commercial license" in notices


def test_package_data_includes_the_font() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'assets/*.ttf' in pyproject
    assert 'dynamic = ["version"]' in pyproject


def test_application_icons_are_present_and_wired_into_the_build() -> None:
    assets = ROOT / "medmask" / "assets"
    for filename in ("app_icon.png", "app_icon.ico", "app_icon.icns"):
        assert (assets / filename).is_file()
    with Image.open(assets / "app_icon.png") as icon:
        assert icon.size == (256, 256)
    builder = (ROOT / "scripts" / "build_native.py").read_text(encoding="utf-8")
    assert "app_icon.icns" in builder
    assert "app_icon.ico" in builder
    assert 'assets/app_icon.png' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_qml_resource_manifest_covers_the_whole_interface() -> None:
    """Каждый QML входит в бинарный Qt-ресурс под стабильным qrc-путём."""
    qml = ROOT / "medmask" / "gui" / "qml"
    assert (qml / "Main.qml").is_file()
    assert (qml / "MedMask" / "qmldir").is_file()
    assert (qml / "MedMask" / "Theme.qml").is_file()

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pattern in ("gui/qml/*.qml", "gui/qml/MedMask/*.qml", "gui/qml/MedMask/qmldir"):
        assert pattern in pyproject
    assert '"medmask.gui"' in pyproject

    qrc = ROOT / "medmask" / "gui" / "qml.qrc"
    aliases = {
        element.attrib["alias"]
        for element in ET.parse(qrc).getroot().iter("file")
    }
    expected = {
        f"medmask/gui/qml/{path.relative_to(qml).as_posix()}"
        for path in qml.rglob("*")
        if path.is_file()
    }
    assert expected <= aliases
    assert "medmask/assets/app_glyph.png" in aliases


def test_qml_compiler_creates_compressed_registerable_resource(tmp_path: Path) -> None:
    generated = tmp_path / "qml_resource.py"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "compile_qml_resources.py"),
            "--output",
            str(generated),
        ],
        cwd=ROOT,
        check=True,
    )

    source = generated.read_text(encoding="utf-8")
    assert "Выберите папку" not in source
    namespace = runpy.run_path(str(generated))
    try:
        assert QResource(":/medmask/gui/qml/Main.qml").isValid()
    finally:
        namespace["qCleanupResources"]()


def test_qt_is_declared_and_pinned() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PySide6" in pyproject
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    for package in ("PySide6==", "PySide6_Addons==", "PySide6_Essentials==", "shiboken6=="):
        assert package in constraints


def test_launch_command_survives_the_new_window() -> None:
    """Команда medmask и пакетный режим не зависят от выбора интерфейса."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'medmask = "medmask.launcher:main"' in pyproject
    entry = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "from medmask.launcher import main" in entry
    assert '"--batch"' in entry
    launcher = (ROOT / "medmask" / "launcher.py").read_text(encoding="utf-8")
    assert "MEDMASK_UI" in launcher


def test_native_build_does_not_request_unused_qt_modules() -> None:
    """Сборщик просит только QML-плагины, не браузер, 3D и мультимедиа."""
    builder = (ROOT / "scripts" / "build_native.py").read_text(encoding="utf-8")
    assert '"--include-qt-plugins=qml"' in builder
    for module in ("QtWebEngine", "QtMultimedia", "Qt3D", "QtQuick3D"):
        assert module in builder
    assert "--noinclude-data-files=" in builder
    assert "--noinclude-dlls=" in builder
    assert "QT_DROP" in builder
    assert '"webengine"' in builder
    assert '"qtpdf"' in builder


def test_native_build_excludes_unused_gui_and_ocr_backends() -> None:
    builder = (ROOT / "scripts" / "build_native.py").read_text(encoding="utf-8")
    assert "--enable-plugin=tk-inter" not in builder
    for module in (
        "medmask.app",
        "tkinter",
        "rapidocr.inference_engine.pytorch",
        "rapidocr.inference_engine.openvino",
        "rapidocr.inference_engine.tensorrt",
    ):
        assert module in builder


def test_windows_native_output_is_used_without_destructive_rename() -> None:
    builder = (ROOT / "scripts" / "build_native.py").read_text(encoding="utf-8")
    assert 'bundle = DIST / "MedMask"' in builder
    assert 'executable = bundle / "MedMask.exe"' in builder
    assert "raw.replace(bundle)" not in builder


@pytest.mark.parametrize(
    "path",
    [
        "scripts/build_macos.command",
        "scripts/build_windows.ps1",
        "scripts/build_native.py",
        ".github/workflows/build-desktop.yml",
    ],
)
def test_build_files_do_not_hardcode_the_version(path: str) -> None:
    assert __version__ not in (ROOT / path).read_text(encoding="utf-8")


def test_native_builder_is_the_single_build_definition() -> None:
    for script in ("scripts/build_macos.command", "scripts/build_windows.ps1"):
        contents = (ROOT / script).read_text(encoding="utf-8")
        assert "build_native.py" in contents
        assert "verify_protected_build.py" in contents
        assert "test_all.py" in contents
    workflow = (ROOT / ".github/workflows/build-desktop.yml").read_text(encoding="utf-8")
    assert "build_native.py" in workflow
    assert "verify_protected_build.py" in workflow
    assert "smoke_test.py" in workflow
    assert "scripts/test_all.py" in workflow
    assert "PYMUPDF_COMMERCIAL_LICENSE_CONFIRMED" in workflow

    builder = (ROOT / "scripts" / "build_native.py").read_text(encoding="utf-8")
    for option in (
        "--mode=app-dist",
        "--include-package=medmask",
        "--include-module=rapidocr.main",
        "--include-module=onnxruntime",
        "--include-package-data=rapidocr:config.yaml",
        "--force-runtime-environment-variable=MEDMASK_DISABLE_PARALLEL=1",
        "--assume-yes-for-downloads",
        "--python-flag=no_docstrings",
        "--lto=",
        "--deployment",
        "--remove-output",
    ):
        assert option in builder


def test_macos_signing_happens_after_stripping_without_deep_mode() -> None:
    script = (ROOT / "scripts" / "build_macos.command").read_text(encoding="utf-8")
    assert "codesign --force --deep" not in script
    executable_sign = "codesign --force --sign - dist/MedMask.app/Contents/MacOS/MedMaskCore"
    bundle_sign = "codesign --force --sign - dist/MedMask.app"
    lines = script.splitlines()
    assert executable_sign in lines
    assert bundle_sign in lines
    assert lines.index(executable_sign) < lines.index(bundle_sign)


def test_release_checks_include_static_analysis_and_isolated_gui_suites() -> None:
    script = (ROOT / "scripts" / "test_all.py").read_text(encoding="utf-8")
    assert '"ruff", "check"' in script
    assert '"tests/test_ui.py"' in script
    assert '"tests/test_gui.py"' in script

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert "pytest>=9.0.3" in pyproject
    assert "pytest==9.0.3" in constraints
    assert "ruff==0.16.4" in constraints
    assert "Nuitka==4.1.3" in constraints
    assert "pyinstaller" not in constraints.lower()


def test_unsafe_legacy_batch_entry_point_is_absent() -> None:
    source = (ROOT / "medmask" / "depersonalizer.py").read_text(encoding="utf-8")
    assert "def write_audit_report" not in source
    assert 'if __name__ == "__main__"' not in source


def test_builds_use_the_tested_dependency_constraints() -> None:
    constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    assert "rapidocr==3.9.2" in constraints
    assert "onnxruntime==1.28.0" in constraints
    for path in (
        "scripts/build_macos.command",
        "scripts/build_windows.ps1",
        ".github/workflows/build-desktop.yml",
    ):
        assert "constraints.txt" in (ROOT / path).read_text(encoding="utf-8")


def test_generated_resource_and_old_spec_do_not_enter_the_repository() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "medmask/gui/_qml_resources.py" in ignore
    assert not (ROOT / "MedMask.spec").exists()
    assert not list((ROOT / "hooks").glob("hook-*.py"))


def test_smoke_fixture_contains_personal_data_to_mask() -> None:
    fixture = ROOT / "tests" / "fixtures" / "smoke"
    documents = list(fixture.glob("*.txt"))
    assert documents
    text = documents[0].read_text(encoding="utf-8")
    assert re.search(r"\d{2}\.\d{2}\.\d{4}", text)
    assert "СНИЛС" in text


def test_batch_mode_survives_without_stdout(tmp_path, monkeypatch) -> None:
    """В оконной сборке stdout нет; пакетный режим не должен падать из-за печати."""
    import main as entry_point

    source = tmp_path / "Карты"
    source.mkdir()
    (source / "История.txt").write_text(
        "Пациент: Иванов Иван Иванович\nДиагноз: ОНМК.\n", encoding="utf-8"
    )
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    monkeypatch.setattr("sys.argv", ["MedMask", "--batch", str(source)])
    assert entry_point.run() == 0
    assert list((tmp_path / "Обезличенные").glob("*.pdf"))


def test_batch_mode_does_not_print_sensitive_unknown_errors(monkeypatch) -> None:
    import main as entry_point

    secret = "/Users/doctor/Иванов Иван Иванович.pdf"

    def fail(_source):
        raise RuntimeError(secret)

    stderr = io.StringIO()
    monkeypatch.setattr("medmask.batch.process_folder", fail)
    monkeypatch.setattr("sys.stderr", stderr)
    monkeypatch.setattr("sys.argv", ["MedMask", "--batch", "/tmp/Карты"])

    assert entry_point.run() == 1
    assert secret not in stderr.getvalue()
    assert stderr.getvalue().strip() == "Не удалось завершить обработку."
