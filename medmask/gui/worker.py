"""Фоновые потоки: обход папки и пакетная обработка.

Движок остается прежним — потоки только вызывают medmask.batch и переносят
его сообщения в главный поток сигналами Qt. Так окно не замирает во время OCR.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# Движок сообщает о каждой странице. Окну хватает частоты кадров, поэтому
# промежуточные сообщения прореживаются, а события с исходом документа
# проходят всегда: на них держится состояние строки.
_MIN_INTERVAL = 1 / 30


class ScanWorker(QThread):
    """Обход выбранной папки. Долгий на сетевых дисках, поэтому в потоке."""

    ready = Signal(int, object, object)

    def __init__(self, source_dir: Path, token: int, parent=None) -> None:
        super().__init__(parent)
        self._source_dir = source_dir
        self._token = token

    def run(self) -> None:  # pragma: no cover — поток проверяется через контроллер
        from ..batch import discover_files

        try:
            files, skipped = discover_files(self._source_dir)
        except OSError:
            files, skipped = [], {}
        self.ready.emit(self._token, files, skipped)


class BatchWorker(QThread):
    """Один запуск обезличивания папки."""

    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(object)

    def __init__(self, source_dir: Path, discovered=None, parent=None) -> None:
        super().__init__(parent)
        self._source_dir = source_dir
        self._discovered = discovered
        self._cancel = threading.Event()
        self._last_emit = 0.0

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:  # pragma: no cover — поток проверяется через контроллер
        from ..batch import process_folder

        try:
            result = process_folder(
                self._source_dir,
                on_progress=self._report,
                is_cancelled=self._cancel.is_set,
                discovered=self._discovered,
            )
        except Exception as error:  # noqa: BLE001 — окно показывает любую ошибку
            self.failed.emit(error)
            return
        self.completed.emit(result)

    def _report(self, progress) -> None:
        now = time.monotonic()
        if not progress.outcome and now - self._last_emit < _MIN_INTERVAL:
            return
        self._last_emit = now
        self.progress.emit(progress)
