"""Снимки окна во всех состояниях без запуска движка.

Показывает то же окно, что видит пользователь, но состояния переключает
подставными потоками: обработка не запускается, зато каждое состояние можно
рассмотреть и сравнить на разных размерах окна и масштабах экрана.

    python scripts/preview_ui.py --out /tmp/preview --size 760x600
    QT_SCALE_FACTOR=1.5 python scripts/preview_ui.py --out /tmp/preview-150
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from medmask.batch import BatchCancelled, BatchResult, FileResult, MedMaskError, Progress  # noqa: E402
from medmask.gui.application import configure_application, create_engine  # noqa: E402
from medmask.gui.controller import Controller  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402

OUTPUT_DIR = Path(tempfile.gettempdir()) / "Обезличенные 2026-08-25 18-40"

DOCUMENTS = [
    "Иванов_И_И_выписка.pdf",
    "Лабораторные_анализы.xlsx",
    "История_болезни_042.docx",
    "Снимок_заключение.png",
    "Направление_на_МРТ.pdf",
    "Карта_пациента.rtf",
    "Протокол_осмотра_невролога.docx",
    "Выписной_эпикриз_2026.pdf",
    "Результаты_ЭКГ.txt",
    "Консультация_кардиолога.odt",
]


class StubScan(QObject):
    ready = Signal(int, object, object)

    def __init__(self, source_dir, token, parent=None) -> None:
        super().__init__(parent)
        self.source_dir = source_dir
        self.token = token

    def start(self) -> None:
        pass

    def wait(self, timeout: int = 0) -> bool:
        return True


class StubBatch(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)

    def __init__(self, source_dir, discovered=None, parent=None) -> None:
        super().__init__(parent)
        self.source_dir = source_dir

    def start(self) -> None:
        pass

    def cancel(self) -> None:
        pass

    def wait(self, timeout: int = 0) -> bool:
        return True


def _files(source: Path) -> list[Path]:
    return [source / name for name in DOCUMENTS]


def _result(source: Path, *, review: bool, broken: bool) -> BatchResult:
    output = OUTPUT_DIR
    items: list[FileResult] = []
    for number, name in enumerate(DOCUMENTS, start=1):
        item = FileResult(number=number, source_path=source / name)
        if broken and number > 1:
            item.error = "не удалось прочитать формат документа"
        else:
            item.output_path = output / f"document_{number:04d}.pdf"
        if review and number in (4, 5):
            item.ocr_pages = [1]
            item.scan_pages = [1]
        if review and number == 3:
            item.low_confidence_pages = [2]
        items.append(item)
    return BatchResult(
        source_dir=source,
        output_dir=output,
        files=items,
        skipped_by_extension={".dcm": 2} if review else {},
        report_path=output / "_ОТЧЁТ.txt",
    )


def build_states(controller: Controller, source: Path):
    files = _files(source)
    skipped = {".dcm": 2}

    def reset():
        """Каждое состояние показывается с чистого листа, а не поверх прошлого."""
        controller._output_dir = None
        controller._documents.clear()
        controller._skipped = 0
        controller._started_at = None
        controller._elapsed = 0.0
        controller._percent = 0
        controller._progress = 0.0
        controller._indeterminate = False
        controller._progress_tone = "primary"
        controller._eta_text = ""
        controller._source_dir = None
        controller._set_stage("Выберите папку с медицинскими документами", "muted")
        controller._apply_state("idle")
        controller.progressChanged.emit()

    def scan_ready(found):
        reset()
        controller._source_dir = source
        controller._on_scan_ready(controller._scan_token, found, skipped)

    def go_running():
        scan_ready(files)
        controller.start()
        controller._started_at = time.monotonic() - 24
        for number in (1, 2):
            controller._documents.update_file(number, outcome="done")
        controller._documents.update_file(3, stage="Распознавание скана")
        controller._on_progress(
            Progress(
                completed=2,
                total=len(files),
                current_name=DOCUMENTS[2],
                stage="Извлечение и обезличивание",
                overall_fraction=0.68,
                number=3,
            )
        )

    def go_cancelling():
        go_running()
        controller.cancel()

    def go_done(review: bool):
        go_running()
        controller._on_completed(_result(source, review=review, broken=False))

    def go_failed(error):
        go_running()
        controller._percent = 18
        controller._progress = 0.18
        controller._on_failed(error)

    return [
        ("01-папка-не-выбрана", reset),
        ("02-чтение-папки", lambda: (reset(), controller.set_folder(source))),
        ("03-нет-документов", lambda: scan_ready([])),
        ("04-готово-к-запуску", lambda: scan_ready(files)),
        ("05-идет-обработка", go_running),
        ("06-отмена", go_cancelling),
        ("07-успех", lambda: go_done(False)),
        ("08-нужна-проверка", lambda: go_done(True)),
        ("09-ошибка", lambda: go_failed(MedMaskError("В сборке отсутствует модуль обработки PDF."))),
        ("10-отменено", lambda: go_failed(BatchCancelled("Обработка отменена."))),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="preview")
    parser.add_argument("--size", default="760x600")
    parser.add_argument("--settle", type=int, default=420)
    arguments = parser.parse_args()

    width, height = (int(part) for part in arguments.size.lower().split("x"))
    out_dir = Path(arguments.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    QQuickWindow.setDefaultAlphaBuffer(True)
    QQuickWindow.setTextRenderType(QQuickWindow.TextRenderType.QtTextRendering)
    application = QGuiApplication(sys.argv)
    configure_application(application)
    controller = Controller(scan_factory=StubScan, batch_factory=StubBatch)
    engine, controller = create_engine(application, controller)
    window = engine.rootObjects()[0]
    window.setWidth(width)
    window.setHeight(height)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    source = Path.home() / "Documents" / "Истории пациентов"
    states = build_states(controller, source)
    index = 0

    def step() -> None:
        nonlocal index
        if index >= len(states):
            application.quit()
            return
        name, apply_state = states[index]
        index += 1
        apply_state()
        QTimer.singleShot(arguments.settle, lambda: capture(name))

    def capture(name: str) -> None:
        image = window.grabWindow()
        # При системном стекле окно прозрачно: на снимке под него
        # подкладывается ровный фон, иначе видно только альфу.
        if image.hasAlphaChannel():
            image.setDevicePixelRatio(1)
            flat = QImage(image.size(), QImage.Format.Format_RGB32)
            # Примерно такой светлый матовый лист дает материал macOS.
            flat.fill(QColor("#E6E9EF"))
            painter = QPainter(flat)
            painter.drawImage(0, 0, image)
            painter.end()
            image = flat
        path = out_dir / f"{name}.png"
        image.save(str(path))
        print(f"{path}  {image.width()}×{image.height()}")
        QTimer.singleShot(60, step)

    QTimer.singleShot(700, step)
    application.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
