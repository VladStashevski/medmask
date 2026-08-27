"""Проверка собранного приложения на живом документе.

Запускает готовый MedMask в пакетном режиме и убеждается, что PDF создан,
персональные данные из него исчезли, а клинический текст остался. Так ловятся
поломки, которые не видны на машине разработчика: не попавшие в сборку модели
OCR, отсутствующий шрифт или сломанный хук.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Консоль Windows по умолчанию не в UTF-8, и кириллица в сообщениях роняет
# скрипт с UnicodeEncodeError уже после успешной проверки.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "smoke"
FONT = ROOT / "medmask" / "assets" / "LiberationSans-Regular.ttf"
PERSONAL_DATA = (
    "Ковалёв", "Артём", "Сергеевич", "14.03.1968", "Ленина",
    "912", "123-456-789", "1234567890123456", "Петров",
    "Смолина", "Елена", "12.04.1970",
)
CLINICAL_TEXT = (
    "ишемический инсульт",
    "Температура тела",
    "контрольное распознавание текста",
)


def _print_safe_report(output_dir: Path) -> None:
    report_path = output_dir / "_ОТЧЁТ.txt"
    if report_path.is_file():
        print(report_path.read_text(encoding="utf-8-sig"), file=sys.stderr)


def _create_ocr_fixture(source: Path, pymupdf) -> None:
    """Растеризует стабильный кириллический текст — в PNG нет текстового слоя."""
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        page.insert_font(fontname="fixture", fontfile=str(FONT))
        lines = (
            "Пациент: Смолина Елена Петровна",
            "Дата рождения: 12.04.1970",
            "Диагноз: контрольное распознавание текста",
        )
        for index, line in enumerate(lines):
            page.insert_text(
                (54, 100 + index * 52),
                line,
                fontname="fixture",
                fontsize=24,
            )
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        pixmap.save(source / "OCR-проверка.png")


def main(command: list[str]) -> int:
    import pymupdf

    with tempfile.TemporaryDirectory() as workdir:
        source = Path(workdir) / "Карты"
        shutil.copytree(FIXTURE, source)
        _create_ocr_fixture(source, pymupdf)
        text_fixture = next(source.glob("*.txt"))
        for index in (1, 2):
            shutil.copy2(text_fixture, source / f"Повтор_{index}.txt")

        run = subprocess.run(
            [*command, "--batch", str(source)],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if run.returncode != 0:
            print(f"приложение завершилось с кодом {run.returncode}", file=sys.stderr)
            print(run.stdout, run.stderr, file=sys.stderr)
            return 1

        output_dir = Path(workdir) / "Обезличенные"
        pdfs = sorted(output_dir.glob("*.pdf"))
        if len(pdfs) != 4:
            print(f"ожидалось 4 PDF, создано {len(pdfs)}", file=sys.stderr)
            _print_safe_report(output_dir)
            return 1
        if not (output_dir / "_ОТЧЁТ.txt").is_file():
            print("отчёт не создан", file=sys.stderr)
            return 1
        report = (output_dir / "_ОТЧЁТ.txt").read_text(encoding="utf-8-sig")
        if "OCR применён: документов 1, страниц 1" not in report:
            print("собранное приложение не подтвердило OCR тестового скана", file=sys.stderr)
            return 1

        text = "\n".join(
            page.get_text() for pdf in pdfs for page in pymupdf.open(pdf)
        )
        leaked = [value for value in PERSONAL_DATA if value in text]
        if leaked:
            print("в результате остались персональные данные: " + ", ".join(leaked), file=sys.stderr)
            return 1
        lost = [value for value in CLINICAL_TEXT if value not in text]
        if lost:
            print("из результата пропал клинический текст: " + ", ".join(lost), file=sys.stderr)
            return 1

        fonts = {font[3] for pdf in pdfs for page in pymupdf.open(pdf) for font in page.get_fonts()}
        print(f"проверено PDF: {len(pdfs)}, шрифты: {', '.join(sorted(fonts))}")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Запуск: smoke_test.py <путь к собранному MedMask>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
