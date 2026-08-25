"""Создаёт runtime PNG и системные иконки из одного исходника."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "medmask" / "assets"
SOURCE = ASSET_DIR / "app_icon_source.png"


def main() -> int:
    with Image.open(SOURCE) as opened:
        source = opened.convert("RGB")

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
