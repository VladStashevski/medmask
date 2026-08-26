"""Создает значок окна и системные иконки из векторных исходников.

Исходники — `app_icon.svg` (плитка на белом поле, из нее растут иконки для
Dock, Finder и панели задач) и `app_glyph.svg` (тот же рисунок без подложки,
для шапки окна: там фон уже есть, и белая плитка на нем выглядела наклейкой).

Прозрачность сохраняется на всем пути: у плитки скруглены углы, и сведение к
RGB залило бы их черным — в Dock иконка стала бы квадратной.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QRectF  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "medmask" / "assets"
ICON_SVG = ASSET_DIR / "app_icon.svg"
GLYPH_SVG = ASSET_DIR / "app_glyph.svg"
SOURCE = ASSET_DIR / "app_icon_source.png"

# Значок в шапке рисуется в 18 логических пикселей. Запас до 144 — на экраны
# с тройной плотностью и на будущее, если значок вырастет.
GLYPH_SIZE = 144
SOURCE_SIZE = 1024


def render(svg: Path, target: Path, size: int) -> None:
    renderer = QSvgRenderer(str(svg))
    if not renderer.isValid():
        raise SystemExit(f"Не читается {svg.name}")
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    if not image.save(str(target), "PNG"):
        raise SystemExit(f"Не сохраняется {target.name}")


def main() -> int:
    QGuiApplication(sys.argv)

    render(ICON_SVG, SOURCE, SOURCE_SIZE)
    render(GLYPH_SVG, ASSET_DIR / "app_glyph.png", GLYPH_SIZE)

    with Image.open(SOURCE) as opened:
        source = opened.convert("RGBA")

    if source.width != source.height or source.width < 1024:
        raise SystemExit("Исходник иконки должен быть квадратным и не меньше 1024 px.")

    resampling = Image.Resampling.LANCZOS
    source.resize((256, 256), resampling).save(
        ASSET_DIR / "app_icon.png",
        format="PNG",
        optimize=True,
    )
    source.save(
        ASSET_DIR / "app_icon.ico",
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )

    icns_sizes = (32, 64, 128, 256, 512, 1024)
    icns_images = [source.resize((size, size), resampling) for size in icns_sizes]
    icns_images[-1].save(
        ASSET_DIR / "app_icon.icns",
        format="ICNS",
        append_images=icns_images[:-1],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
