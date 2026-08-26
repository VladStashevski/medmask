"""Проверки поставки: встроенные ресурсы и единственная версия."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from PIL import Image

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
    spec = (ROOT / "MedMask.spec").read_text(encoding="utf-8")
    assert "app_icon.icns" in spec
    assert "app_icon.ico" in spec
    assert 'assets/app_icon.png' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_interface_files_are_bundled() -> None:
    """QML читается с диска, поэтому обязан попасть и в пакет, и в сборку."""
    qml = ROOT / "medmask" / "gui" / "qml"
    assert (qml / "Main.qml").is_file()
    assert (qml / "MedMask" / "qmldir").is_file()
    assert (qml / "MedMask" / "Theme.qml").is_file()

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pattern in ("gui/qml/*.qml", "gui/qml/MedMask/*.qml", "gui/qml/MedMask/qmldir"):
        assert pattern in pyproject
    assert '"medmask.gui"' in pyproject

    spec = (ROOT / "MedMask.spec").read_text(encoding="utf-8")
    assert "gui/qml/MedMask/*.qml" in spec
    assert "PySide6.QtQuick" in spec


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


def test_unused_qt_modules_stay_out_of_the_build() -> None:
    """Без списка исключений в сборку уезжает браузерный движок Qt."""
    spec = (ROOT / "MedMask.spec").read_text(encoding="utf-8")
    for module in ("QtWebEngineCore", "QtMultimedia", "Qt3DRender", "QtQuick3D"):
        assert module in spec


@pytest.mark.parametrize(
    "path",
    ["scripts/build_macos.command", "scripts/build_windows.ps1", "MedMask.spec"],
)
def test_build_files_do_not_hardcode_the_version(path: str) -> None:
    assert __version__ not in (ROOT / path).read_text(encoding="utf-8")


def test_spec_is_the_single_build_definition() -> None:
    for script in ("scripts/build_macos.command", "scripts/build_windows.ps1"):
        assert "MedMask.spec" in (ROOT / script).read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/build-desktop.yml").read_text(encoding="utf-8")
    assert "MedMask.spec" in workflow
    assert "smoke_test.py" in workflow


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


def test_spec_is_tracked_by_git() -> None:
    """Файл сборки не должен попадать под общее правило *.spec в .gitignore."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "!MedMask.spec" in ignore


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
