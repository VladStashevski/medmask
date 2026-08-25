"""Проверки поставки: встроенные ресурсы и единственная версия."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

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
