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

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "smoke"
PERSONAL_DATA = (
    "Ковалёв", "Артём", "Сергеевич", "14.03.1968", "Ленина",
    "912", "123-456-789", "1234567890123456", "Петров",
)
CLINICAL_TEXT = ("ишемический инсульт", "Температура тела")


def main(command: list[str]) -> int:
    import pymupdf

    with tempfile.TemporaryDirectory() as workdir:
        source = Path(workdir) / "Карты"
        shutil.copytree(FIXTURE, source)

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
        if not pdfs:
            print(f"в {output_dir} нет ни одного PDF", file=sys.stderr)
            return 1
        if not (output_dir / "_ОТЧЁТ.txt").is_file():
            print("отчёт не создан", file=sys.stderr)
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
