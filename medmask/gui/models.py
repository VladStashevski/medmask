"""Список документов для QML.

Модель держит по строке на каждый найденный файл и обновляется по номеру:
в параллельном режиме сообщения о разных документах приходят вперемешку, и
номер остается единственным надежным ключом.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Slot

from .shell import kind_of

# Подпись состояния справа в строке. Этап конкретного документа («Распознавание
# скана») показывается вместо общего слова, пока файл в работе.
STATUS_TEXT = {
    "": "Ожидает",
    "active": "Анализ",
    "done": "Обезличено",
    "review": "Проверить",
    "failed": "Ошибка",
}

# Этапы движка названы для отчета и в колонку состояния не помещаются.
# В строке нужно одно слово: подробности все равно идут в нижней панели.
SHORT_STAGE = {
    "Чтение документа": "Чтение",
    "Распознавание скана": "Распознавание",
    "Извлечение и обезличивание": "Анализ",
    "Создание нового PDF": "Сборка PDF",
    "Подготовка документа": "Подготовка",
    "Документ готов": "Готово",
    "Ошибка документа": "Ошибка",
}


def short_stage(stage: str) -> str:
    return SHORT_STAGE.get(stage, "Анализ")


def _clean_badge(badge: str, status: str) -> str:
    """Убирает из пометки то, что уже сказано подписью состояния.

    Движок отдает «OCR  ·  проверить», а в строке рядом уже стоит «Проверить»:
    два одинаковых слова подряд читаются как ошибка верстки.
    """
    if not badge:
        return ""
    marks = [mark for mark in badge.split("  ·  ") if mark]
    if status in ("review", "failed"):
        marks = [mark for mark in marks if mark != "проверить"]
    return "  ·  ".join(marks)


class Document:
    __slots__ = ("name", "kind", "status", "stage", "badge")

    def __init__(self, name: str) -> None:
        self.name = name
        self.kind = kind_of(name)
        self.status = ""      # "", active, done, review, failed
        self.stage = ""
        self.badge = ""


class DocumentModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    KindRole = Qt.ItemDataRole.UserRole + 2
    StatusRole = Qt.ItemDataRole.UserRole + 3
    StatusTextRole = Qt.ItemDataRole.UserRole + 4
    BadgeRole = Qt.ItemDataRole.UserRole + 5

    countChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[Document] = []

    # ---------- QAbstractListModel ----------

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008 — подпись Qt
        return 0 if parent.isValid() else len(self._items)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.NameRole: QByteArray(b"name"),
            self.KindRole: QByteArray(b"kind"),
            self.StatusRole: QByteArray(b"status"),
            self.StatusTextRole: QByteArray(b"statusText"),
            self.BadgeRole: QByteArray(b"badge"),
        }

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.NameRole:
            return item.name
        if role == self.KindRole:
            return item.kind
        if role == self.StatusRole:
            return item.status
        if role == self.StatusTextRole:
            if item.status == "active" and item.stage:
                return short_stage(item.stage)
            return STATUS_TEXT.get(item.status, STATUS_TEXT[""])
        if role == self.BadgeRole:
            return _clean_badge(item.badge, item.status)
        return None

    # ---------- обновления ----------

    @Slot(result=int)
    def count(self) -> int:
        return len(self._items)

    def set_files(self, files: list[Path] | list[str]) -> None:
        self.beginResetModel()
        self._items = [
            Document(item.name if isinstance(item, Path) else str(item)) for item in files
        ]
        self.endResetModel()
        self.countChanged.emit()

    def clear(self) -> None:
        self.set_files([])

    def reset_progress(self) -> None:
        """Возвращает все строки в «ожидает» перед новым запуском."""
        if not self._items:
            return
        for item in self._items:
            item.status = ""
            item.stage = ""
            item.badge = ""
        self._emit_changed(0, len(self._items) - 1)

    def update_file(
        self,
        number: int,
        stage: str = "",
        outcome: str = "",
        badge: str = "",
    ) -> None:
        row = number - 1
        if not 0 <= row < len(self._items):
            return
        item = self._items[row]
        status = outcome or "active"
        changed = item.status != status or item.stage != stage
        item.status = status
        item.stage = stage if status == "active" else ""
        if badge:
            item.badge = badge
            changed = True
        if changed:
            self._emit_changed(row, row)

    def finish(self) -> None:
        """Снимает пометку «в работе» с недоделанных строк после остановки."""
        touched = False
        for item in self._items:
            if item.status == "active":
                item.status = ""
                item.stage = ""
                touched = True
        if touched:
            self._emit_changed(0, len(self._items) - 1)

    def status_of(self, number: int) -> str:
        row = number - 1
        return self._items[row].status if 0 <= row < len(self._items) else ""

    def _emit_changed(self, first: int, last: int) -> None:
        self.dataChanged.emit(
            self.index(first, 0),
            self.index(last, 0),
            [self.StatusRole, self.StatusTextRole, self.BadgeRole],
        )
