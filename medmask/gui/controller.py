"""Состояния окна и связь с движком.

Контроллер не обрабатывает документы сам: он вызывает medmask.batch в
фоновом потоке и переводит его сообщения в свойства, на которые опирается QML.
Все подписи собраны здесь, поэтому состояния можно проверять без окна.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    Property,
    QObject,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from .. import __version__
from .models import DocumentModel
from .shell import breadcrumb, format_duration, open_folder, plural
from .worker import BatchWorker, ScanWorker

# Состояния окна. Порядок соответствует пути пользователя.
IDLE = "idle"              # папка не выбрана
SCANNING = "scanning"      # читаем папку
EMPTY = "empty"            # в папке нет подходящих документов
READY = "ready"            # документы найдены, можно запускать
RUNNING = "running"        # идет обработка
CANCELLING = "cancelling"  # отмена запрошена, движок останавливается
DONE = "done"              # все получилось
REVIEW = "review"          # получилось, но часть документов просит проверки
CANCELLED = "cancelled"    # остановлено пользователем
FAILED = "failed"          # ошибка

FORMATS = "PDF, изображения, DOCX, RTF, ODT, TXT и XLSX"


class Controller(QObject):
    stateChanged = Signal()
    folderChanged = Signal()
    progressChanged = Signal()
    stageChanged = Signal()

    def __init__(
        self,
        parent=None,
        scan_factory=ScanWorker,
        batch_factory=BatchWorker,
    ) -> None:
        super().__init__(parent)
        self._scan_factory = scan_factory
        self._batch_factory = batch_factory

        self._documents = DocumentModel(self)
        self._state = IDLE
        self._source_dir: Path | None = None
        self._output_dir: Path | None = None
        self._discovered = None
        self._skipped = 0
        self._scan_token = 0
        self._scan_worker: ScanWorker | None = None
        self._batch_worker: BatchWorker | None = None

        self._stage_text = ""
        self._stage_tone = "muted"
        self._progress = 0.0
        self._percent = 0
        self._indeterminate = False
        self._progress_tone = "primary"
        self._started_at: float | None = None
        self._elapsed = 0.0
        self._eta_text = ""

        self._clock = QTimer(self)
        self._clock.setInterval(200)
        self._clock.timeout.connect(self._tick)

        self._apply_state(IDLE)
        self._warm_engine()

    # ---------- свойства состояния ----------

    def _get_state(self) -> str:
        return self._state

    def _get_busy(self) -> bool:
        return self._state in (RUNNING, CANCELLING)

    def _get_can_choose(self) -> bool:
        return not self._get_busy()

    def _get_can_start(self) -> bool:
        return self._state in (READY, DONE, REVIEW, CANCELLED, FAILED) and self._documents.count() > 0

    def _get_can_cancel(self) -> bool:
        return self._state == RUNNING

    def _get_has_result(self) -> bool:
        return self._output_dir is not None and self._output_dir.exists()

    def _get_show_list(self) -> bool:
        return self._documents.count() > 0

    def _get_empty_kind(self) -> str:
        if self._documents.count() > 0:
            return ""
        if self._state == SCANNING:
            return "scan"
        if self._state == EMPTY:
            return "none"
        if self._state == FAILED:
            return "error"
        return "folder"

    def _get_empty_title(self) -> str:
        return {
            "scan": "Читаем папку",
            "none": "Нет подходящих документов",
            "error": "Обработка не начата",
            "folder": "Папка не выбрана",
        }.get(self._get_empty_kind(), "")

    def _get_empty_hint(self) -> str:
        kind = self._get_empty_kind()
        if kind == "folder":
            # Пояснение уже стоит в нижней панели, второй раз посреди окна
            # оно только заполняет место.
            return ""
        if kind == "none":
            return f"Подходят {FORMATS}"
        if kind == "error":
            return self._stage_text
        return ""

    # ---------- свойства папки ----------

    def _get_has_folder(self) -> bool:
        return self._source_dir is not None

    def _get_folder_name(self) -> str:
        if self._source_dir is None:
            return "Папка не выбрана"
        return self._source_dir.name or str(self._source_dir)

    def _get_folder_path(self) -> str:
        if self._source_dir is None:
            return "Нажмите «Выбрать папку»"
        return breadcrumb(self._source_dir)

    def _get_folder_full(self) -> str:
        return "" if self._source_dir is None else str(self._source_dir)

    def _get_count_compact(self) -> str:
        found = self._documents.count()
        if self._state == SCANNING:
            return "подсчет файлов"
        if not found:
            return ""
        return f"{found} {plural(found, 'документ', 'документа', 'документов')}"

    def _get_count_label(self) -> str:
        compact = self._get_count_compact()
        if not compact or not self._skipped or self._state == SCANNING:
            return compact
        return f"{compact}  ·  {self._skipped} без поддержки"

    def _get_initial_folder(self) -> QUrl:
        if self._source_dir is not None:
            return QUrl.fromLocalFile(str(self._source_dir))
        return QUrl.fromLocalFile(str(Path.home()))

    # ---------- свойства прогресса ----------

    def _get_progress(self) -> float:
        return self._progress

    def _get_percent_text(self) -> str:
        return f"{self._percent}%" if self._state != IDLE and self._percent else ""

    def _get_time_text(self) -> str:
        return format_duration(self._elapsed) if self._started_at is not None else ""

    def _get_eta_text(self) -> str:
        return self._eta_text

    def _get_indeterminate(self) -> bool:
        return self._indeterminate

    def _get_progress_tone(self) -> str:
        return self._progress_tone

    def _get_stage_text(self) -> str:
        return self._stage_text

    def _get_stage_tone(self) -> str:
        return self._stage_tone

    def _get_documents(self) -> DocumentModel:
        return self._documents

    def _get_version(self) -> str:
        return __version__

    state = Property(str, _get_state, notify=stateChanged)
    busy = Property(bool, _get_busy, notify=stateChanged)
    canChoose = Property(bool, _get_can_choose, notify=stateChanged)
    canStart = Property(bool, _get_can_start, notify=stateChanged)
    canCancel = Property(bool, _get_can_cancel, notify=stateChanged)
    hasResult = Property(bool, _get_has_result, notify=stateChanged)
    showList = Property(bool, _get_show_list, notify=stateChanged)
    emptyKind = Property(str, _get_empty_kind, notify=stateChanged)
    emptyTitle = Property(str, _get_empty_title, notify=stateChanged)
    emptyHint = Property(str, _get_empty_hint, notify=stateChanged)

    hasFolder = Property(bool, _get_has_folder, notify=folderChanged)
    folderName = Property(str, _get_folder_name, notify=folderChanged)
    folderPath = Property(str, _get_folder_path, notify=folderChanged)
    folderFull = Property(str, _get_folder_full, notify=folderChanged)
    countLabel = Property(str, _get_count_label, notify=folderChanged)
    countCompact = Property(str, _get_count_compact, notify=folderChanged)
    initialFolder = Property(QUrl, _get_initial_folder, notify=folderChanged)

    progress = Property(float, _get_progress, notify=progressChanged)
    percentText = Property(str, _get_percent_text, notify=progressChanged)
    timeText = Property(str, _get_time_text, notify=progressChanged)
    etaText = Property(str, _get_eta_text, notify=progressChanged)
    indeterminate = Property(bool, _get_indeterminate, notify=progressChanged)
    progressTone = Property(str, _get_progress_tone, notify=progressChanged)

    stageText = Property(str, _get_stage_text, notify=stageChanged)
    stageTone = Property(str, _get_stage_tone, notify=stageChanged)

    documents = Property(QObject, _get_documents, constant=True)
    version = Property(str, _get_version, constant=True)

    # ---------- действия ----------

    @Slot(QUrl)
    def setFolderUrl(self, url: QUrl) -> None:
        path = url.toLocalFile()
        if path:
            self.set_folder(Path(path))

    def set_folder(self, path: Path) -> None:
        if self._get_busy():
            return
        self._source_dir = path.expanduser().resolve()
        self._output_dir = None
        self._discovered = None
        self._skipped = 0
        self._documents.clear()
        self._reset_progress()
        self._set_stage("Читаем папку", "muted")
        self._apply_state(SCANNING)
        self._scan_token += 1
        worker = self._scan_factory(self._source_dir, self._scan_token, self)
        worker.ready.connect(self._on_scan_ready)
        self._scan_worker = worker
        worker.start()

    @Slot()
    def start(self) -> None:
        if self._source_dir is None or self._get_busy() or not self._documents.count():
            return
        self._output_dir = None
        self._documents.reset_progress()
        self._started_at = time.monotonic()
        self._elapsed = 0.0
        self._eta_text = ""
        self._percent = 0
        self._progress = 0.0
        self._indeterminate = True
        self._progress_tone = "primary"
        self._set_stage("Поиск документов", "muted")
        self._apply_state(RUNNING)
        self.progressChanged.emit()
        self._clock.start()
        worker = self._batch_factory(self._source_dir, self._discovered, self)
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        self._batch_worker = worker
        worker.start()

    @Slot()
    def cancel(self) -> None:
        if self._state != RUNNING or self._batch_worker is None:
            return
        self._batch_worker.cancel()
        self._set_stage("Останавливаем обработку", "warning")
        self._progress_tone = "warning"
        self._apply_state(CANCELLING)
        self.progressChanged.emit()

    @Slot()
    def openResult(self) -> None:
        if self._output_dir is not None and self._output_dir.exists():
            open_folder(self._output_dir)

    @Slot()
    def toggleStart(self) -> None:
        """Одна клавиша на запуск и остановку: Cmd/Ctrl+Enter."""
        if self._get_busy():
            self.cancel()
        else:
            self.start()

    def select_from_arguments(self, argv: list[str] | None = None) -> None:
        arguments = sys.argv[1:] if argv is None else argv
        for candidate in arguments:
            path = Path(candidate).expanduser()
            if path.is_dir():
                self.set_folder(path)
                return

    # ---------- ответы фоновых потоков ----------

    @Slot(int, object, object)
    def _on_scan_ready(self, token: int, files, skipped_by_extension) -> None:
        if token != self._scan_token or self._get_busy():
            return
        self._skipped = sum(skipped_by_extension.values())
        if not files:
            self._discovered = None
            self._documents.clear()
            self._set_stage("В папке нет подходящих документов", "warning")
            self._apply_state(EMPTY)
            return
        self._discovered = (files, skipped_by_extension)
        self._documents.set_files(files)
        # Нижняя строка молчит, пока нечего сказать: до запуска она бы просто
        # повторяла то, что и так написано в окне.
        self._set_stage("", "muted")
        self._apply_state(READY)

    @Slot(object)
    def _on_progress(self, progress) -> None:
        if progress.number:
            self._documents.update_file(
                progress.number,
                stage=progress.detail or progress.stage,
                outcome=progress.outcome,
                badge=progress.badge,
            )
        # «Анализ документов» идет до первого процента: полоса в это время
        # не должна прыгать назад к нулю.
        if progress.stage != "Анализ документов" or progress.percent > 0:
            self._percent = progress.percent
            self._progress = progress.percent / 100
            self._indeterminate = False
        self._set_stage(
            f"{progress.stage}  ·  готово {progress.completed} из {progress.total}",
            "muted",
        )
        self._refresh_time()

    @Slot(object)
    def _on_completed(self, result) -> None:
        from ..batch import badge_of, outcome_of

        self._clock.stop()
        self._refresh_time()
        self._output_dir = result.output_dir
        self._batch_worker = None
        for item in result.files:
            self._documents.update_file(
                item.number, outcome=outcome_of(item), badge=badge_of(item)
            )
        self._documents.finish()

        self._percent = 100
        self._progress = 1.0
        self._indeterminate = False
        self._eta_text = ""

        if not result.successful:
            state, tone = FAILED, "danger"
        elif result.needs_review:
            # Обработка прошла, поэтому итог зеленый. Что именно перечитать,
            # видно по строкам: у них свой значок и подпись «Проверить».
            state, tone = REVIEW, "success"
        else:
            state, tone = DONE, "success"
        self._progress_tone = tone
        self._set_stage(self._summary(result), tone)
        self._apply_state(state)
        self.progressChanged.emit()

    @Slot(object)
    def _on_failed(self, error: Exception) -> None:
        from ..batch import BatchCancelled, MedMaskError

        self._clock.stop()
        self._refresh_time()
        self._batch_worker = None
        self._documents.finish()
        self._indeterminate = False
        self._eta_text = ""
        if isinstance(error, BatchCancelled):
            self._progress_tone = "warning"
            self._set_stage("Отменено  ·  исходные файлы не изменены", "warning")
            self._apply_state(CANCELLED)
        else:
            self._progress_tone = "danger"
            message = (
                str(error)
                if isinstance(error, MedMaskError)
                else "Не удалось завершить обработку  ·  исходные файлы не изменены"
            )
            self._set_stage(message, "danger")
            self._apply_state(FAILED)
        self.progressChanged.emit()

    # ---------- вспомогательное ----------

    @staticmethod
    def _summary(result) -> str:
        successful = result.successful
        parts = [f"{successful} {plural(successful, 'файл', 'файла', 'файлов')}"]
        if result.recognized_with_ocr:
            parts.append(f"OCR {result.recognized_with_ocr}")
        if result.needs_review:
            parts.append(f"проверить {len(result.needs_review)}")
        if result.failed:
            parts.append(f"с ошибкой {result.failed}")
        skipped = sum(result.skipped_by_extension.values())
        if skipped:
            parts.append(f"пропущено {skipped}")
        # Имя созданной папки прямо в итоге: не нужно гадать, куда лег результат.
        parts.append(result.output_dir.name)
        head = "Готово" if successful else "Ничего не создано"
        return f"{head}  ·  " + "  ·  ".join(parts)

    def _reset_progress(self) -> None:
        self._progress = 0.0
        self._percent = 0
        self._indeterminate = False
        self._progress_tone = "primary"
        self._started_at = None
        self._elapsed = 0.0
        self._eta_text = ""
        self.progressChanged.emit()

    def _set_stage(self, text: str, tone: str = "muted") -> None:
        if text == self._stage_text and tone == self._stage_tone:
            return
        self._stage_text = text
        self._stage_tone = tone
        self.stageChanged.emit()

    def _apply_state(self, state: str) -> None:
        self._state = state
        self.stateChanged.emit()
        self.folderChanged.emit()

    def _tick(self) -> None:
        self._refresh_time()

    def _refresh_time(self) -> None:
        if self._started_at is None:
            return
        self._elapsed = time.monotonic() - self._started_at
        seconds = int(self._elapsed)
        percent = self._percent
        eta = ""
        if self._get_busy() and 2 <= percent < 100 and seconds >= 3:
            remaining = round(seconds * (100 - percent) / percent)
            eta = f"осталось ~{format_duration(remaining)}"
        self._eta_text = eta
        self.progressChanged.emit()

    def _warm_engine(self) -> None:
        """Тянет тяжелые модули заранее: окно появляется сразу, а к моменту
        выбора папки движок уже в памяти."""
        import threading

        def warm() -> None:
            try:
                from .. import batch  # noqa: F401
            except Exception:
                pass

        threading.Thread(target=warm, daemon=True).start()

    def shutdown(self) -> None:
        """Останавливает потоки, чтобы закрытие окна не роняло процесс."""
        if self._batch_worker is not None:
            self._batch_worker.cancel()
            self._batch_worker.wait(3000)
        if self._scan_worker is not None:
            self._scan_worker.wait(2000)
