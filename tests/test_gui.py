"""Окно на Qt Quick: состояния, список документов и связь с движком.

Окно поднимается на платформе offscreen, поэтому проверки идут и на машине
разработчика, и на сервере сборки без экрана.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QObject, QtMsgType, Signal, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from medmask.gui.application import QML_DIR, configure_application, create_engine  # noqa: E402
from medmask.gui.environment import Environment  # noqa: E402
from medmask.gui.controller import (  # noqa: E402
    CANCELLED,
    DONE,
    EMPTY,
    FAILED,
    IDLE,
    READY,
    REVIEW,
    RUNNING,
    SCANNING,
    Controller,
)
from medmask.gui.models import DocumentModel, short_stage  # noqa: E402
from medmask.gui.shell import breadcrumb, format_duration, kind_of, plural  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def application():
    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    instance = QGuiApplication([])
    configure_application(instance)
    return instance


class StubScan(QObject):
    """Обход папки без файловой системы: результат подсовывают тесты."""

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

    last: "StubBatch | None" = None

    def __init__(self, source_dir, discovered=None, parent=None) -> None:
        super().__init__(parent)
        self.source_dir = source_dir
        self.discovered = discovered
        self.cancelled = False
        self.started = False
        StubBatch.last = self

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, timeout: int = 0) -> bool:
        return True


@pytest.fixture
def controller(application):
    instance = Controller(scan_factory=StubScan, batch_factory=StubBatch)
    yield instance
    instance.shutdown()


def _scan(controller: Controller, files, skipped=None):
    controller._on_scan_ready(controller._scan_token, files, skipped or {})


def _result(tmp_path: Path, *, review=False, broken=False, count=3):
    from medmask.batch import BatchResult, FileResult

    output = tmp_path / "Обезличенные 2026-08-25 10-00"
    output.mkdir(exist_ok=True)
    items = []
    for number in range(1, count + 1):
        item = FileResult(number=number, source_path=tmp_path / f"файл{number}.txt")
        if broken:
            item.error = "не удалось прочитать формат документа"
        else:
            item.output_path = output / f"document_{number:04d}.pdf"
        if review and number == 2:
            item.low_confidence_pages = [1]
            item.ocr_pages = [1]
        items.append(item)
    return BatchResult(
        source_dir=tmp_path,
        output_dir=output,
        files=items,
        skipped_by_extension={},
        report_path=output / "_ОТЧЁТ.txt",
    )


# ---------- мелкие утилиты ----------


def test_kind_is_taken_from_the_extension() -> None:
    assert kind_of("Выписка.PDF") == "pdf"
    assert kind_of("анализы.xlsm") == "sheet"
    assert kind_of("скан.TIFF") == "image"
    assert kind_of("протокол.docx") == "doc"
    assert kind_of("без расширения") == "text"


def test_breadcrumb_drops_the_home_prefix_and_marks_the_cut() -> None:
    assert breadcrumb(Path.home() / "Documents" / "Карты") == "Documents  /  Карты"
    long_path = Path("/a/b/c/d/e/f")
    assert breadcrumb(long_path).startswith("…")
    assert breadcrumb(long_path).endswith("d  /  e  /  f")


def test_duration_keeps_a_stable_width() -> None:
    assert format_duration(0) == "00:00"
    assert format_duration(59.9) == "00:59"
    assert format_duration(3725) == "1:02:05"


def test_plural_follows_russian_rules() -> None:
    assert plural(1, "документ", "документа", "документов") == "документ"
    assert plural(3, "документ", "документа", "документов") == "документа"
    assert plural(11, "документ", "документа", "документов") == "документов"


# ---------- список ----------


def test_model_exposes_roles_for_qml() -> None:
    model = DocumentModel()
    model.set_files(["Выписка.pdf", "Анализы.xlsx"])
    roles = {bytes(name).decode() for name in model.roleNames().values()}
    assert roles == {"name", "kind", "status", "statusText", "badge"}
    assert model.data(model.index(0, 0), DocumentModel.StatusTextRole) == "Ожидает"


def test_row_shows_a_short_stage_while_working() -> None:
    model = DocumentModel()
    model.set_files(["Выписка.pdf"])
    model.update_file(1, stage="Извлечение и обезличивание")
    assert model.data(model.index(0, 0), DocumentModel.StatusRole) == "active"
    assert model.data(model.index(0, 0), DocumentModel.StatusTextRole) == "Анализ"
    assert short_stage("Распознавание скана") == "Распознавание"


def test_badge_does_not_repeat_the_status_word() -> None:
    model = DocumentModel()
    model.set_files(["Скан.png"])
    model.update_file(1, outcome="review", badge="OCR  ·  проверить")
    assert model.data(model.index(0, 0), DocumentModel.BadgeRole) == "OCR"
    assert model.data(model.index(0, 0), DocumentModel.StatusTextRole) == "Проверить"


def test_finish_clears_rows_left_in_work() -> None:
    model = DocumentModel()
    model.set_files(["a.txt", "b.txt"])
    model.update_file(1, outcome="done")
    model.update_file(2, stage="Чтение документа")
    model.finish()
    assert model.status_of(1) == "done"
    assert model.status_of(2) == ""


# ---------- состояния окна ----------


def test_starts_without_a_folder(controller: Controller) -> None:
    assert controller.state == IDLE
    assert controller.emptyKind == "folder"
    assert not controller.canStart
    assert controller.canChoose
    # Нижняя строка молчит, пока нечего сказать.
    assert controller.stageText == ""


def test_reading_a_folder_then_finding_nothing(controller: Controller, tmp_path: Path) -> None:
    controller.set_folder(tmp_path)
    assert controller.state == SCANNING
    assert controller.countLabel == "подсчет файлов"
    _scan(controller, [], {".dcm": 4})
    assert controller.state == EMPTY
    assert controller.emptyKind == "none"
    assert not controller.canStart


def test_ready_lists_the_documents(controller: Controller, tmp_path: Path) -> None:
    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / "Выписка.pdf", tmp_path / "Анализы.xlsx"], {".dcm": 1})
    assert controller.state == READY
    assert controller.documents.count() == 2
    assert controller.countLabel == "2 документа  ·  1 без поддержки"
    assert controller.countCompact == "2 документа"
    assert controller.canStart
    assert controller.showList


def test_running_shows_progress_and_blocks_the_folder(controller: Controller, tmp_path: Path) -> None:
    from medmask.batch import Progress

    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / f"файл{n}.txt" for n in range(1, 4)])
    controller.start()
    assert controller.state == RUNNING
    assert controller.busy
    assert not controller.canChoose
    assert controller.indeterminate

    controller._on_progress(
        Progress(completed=1, total=3, current_name="файл2.txt", stage="Чтение документа",
                 overall_fraction=0.4, number=2)
    )
    assert not controller.indeterminate
    assert controller.percentText == "40%"
    assert controller.progress == pytest.approx(0.4)
    assert "готово 1 из 3" in controller.stageText
    assert controller.documents.status_of(2) == "active"


def test_cancel_asks_the_worker_and_shows_the_stop(controller: Controller, tmp_path: Path) -> None:
    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / "файл.txt"])
    controller.start()
    controller.cancel()
    assert controller.state == "cancelling"
    assert StubBatch.last is not None and StubBatch.last.cancelled
    assert not controller.canCancel

    from medmask.batch import BatchCancelled

    controller._on_failed(BatchCancelled("Обработка отменена."))
    assert controller.state == CANCELLED
    assert controller.stageTone == "warning"
    assert controller.canStart


def test_success_offers_the_result(controller: Controller, tmp_path: Path) -> None:
    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / f"файл{n}.txt" for n in range(1, 4)])
    controller.start()
    controller._on_completed(_result(tmp_path))
    assert controller.state == DONE
    assert controller.stageTone == "success"
    assert controller.hasResult
    assert controller.progress == 1.0
    assert controller.documents.status_of(1) == "done"


def test_review_is_a_separate_outcome(controller: Controller, tmp_path: Path) -> None:
    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / f"файл{n}.txt" for n in range(1, 4)])
    controller.start()
    controller._on_completed(_result(tmp_path, review=True))
    assert controller.state == REVIEW
    # Обработка прошла — итог зеленый, а разбираться надо по строкам.
    assert controller.stageTone == "success"
    assert "проверить 1" in controller.stageText
    assert controller.documents.status_of(2) == "review"


def test_engine_error_is_shown_as_is(controller: Controller, tmp_path: Path) -> None:
    from medmask.batch import MedMaskError

    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / "файл.txt"])
    controller.start()
    controller._on_failed(MedMaskError("В сборке отсутствует модуль обработки PDF."))
    assert controller.state == FAILED
    assert controller.stageTone == "danger"
    assert controller.stageText == "В сборке отсутствует модуль обработки PDF."
    assert not controller.hasResult


def test_unknown_error_does_not_leak_details(controller: Controller, tmp_path: Path) -> None:
    controller.set_folder(tmp_path)
    _scan(controller, [tmp_path / "файл.txt"])
    controller.start()
    controller._on_failed(ValueError("/Users/врач/Иванов Иван.pdf"))
    assert controller.state == FAILED
    assert "Иванов" not in controller.stageText


# ---------- связь с настоящим движком ----------


def _spin(application, condition, timeout=180.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return condition()


def test_real_run_produces_pdfs_without_blocking_the_window(application, tmp_path: Path) -> None:
    """Окно проходит весь путь на настоящем движке: обход, обработка, итог."""
    source = tmp_path / "Карты"
    source.mkdir()
    (source / "История.txt").write_text(
        "Пациент: Иванов Иван Иванович\nДата рождения: 14.03.1968\nДиагноз: ОНМК.\n",
        encoding="utf-8",
    )
    instance = Controller()
    try:
        instance.set_folder(source)
        assert _spin(application, lambda: instance.state in (READY, EMPTY), 60)
        assert instance.state == READY
        assert instance.documents.count() == 1

        instance.start()
        assert _spin(application, lambda: instance.state in (DONE, REVIEW, FAILED, CANCELLED))
        assert instance.state in (DONE, REVIEW), instance.stageText
        assert instance.hasResult
        assert instance.documents.status_of(1) in ("done", "review")
        # Папка результата создается рядом с исходной, а не внутри нее.
        output = list(tmp_path.glob("Обезличенные*/*.pdf"))
        assert output, "движок не создал PDF"
    finally:
        instance.shutdown()


# ---------- сам интерфейс ----------


def test_qml_loads_without_warnings(application) -> None:
    messages: list[str] = []

    # Жалобы самой системы на шрифты к интерфейсу отношения не имеют: Qt
    # больше не возит свои шрифты, и на чистой машине без них он ворчит еще
    # до того, как увидит хоть один QML-файл.
    system_noise = ("Populating font family aliases", "QFontDatabase:")

    def collect(mode, context, message):
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if any(noise in message for noise in system_noise):
                return
            messages.append(message)

    previous = qInstallMessageHandler(collect)
    try:
        engine, instance = create_engine(application)
        assert engine.rootObjects(), "Main.qml не загрузился"
        window = engine.rootObjects()[0]
        assert window.width() == 760
        assert window.height() == 600
        assert window.minimumWidth() == 560
        assert window.minimumHeight() == 480
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 200)
        instance.shutdown()
        engine.deleteLater()
    finally:
        qInstallMessageHandler(previous)
    assert not messages, "QML жалуется: " + "; ".join(messages)


def test_every_component_of_the_module_is_declared() -> None:
    module = QML_DIR / "MedMask"
    declared = {
        line.split()[-1]
        for line in (module / "qmldir").read_text(encoding="utf-8").splitlines()
        if line.strip().endswith(".qml")
    }
    present = {path.name for path in module.glob("*.qml")}
    assert declared == present


def test_theme_is_light_only() -> None:
    """Тема одна: ветки под темное оформление не должны вернуться незаметно."""
    module = QML_DIR / "MedMask"
    for path in list(module.glob("*.qml")) + [QML_DIR / "Main.qml"]:
        assert "Theme.dark" not in path.read_text(encoding="utf-8"), path.name
    assert "dark" not in [
        name for name in dir(Environment) if not name.startswith("_")
    ]


def test_tokens_are_not_scattered_across_the_components() -> None:
    """Числа и цвета живут в Theme.qml, иначе оформление разъезжается."""
    import re

    module = QML_DIR / "MedMask"
    colors: list[str] = []
    for path in list(module.glob("*.qml")) + [QML_DIR / "Main.qml"]:
        if path.name == "Theme.qml":
            continue
        text = path.read_text(encoding="utf-8")
        # Белый и черный допустимы: это знак на цветном кружке и опорный
        # цвет для градиента прозрачности, а не отдельная палитра.
        colors += [
            found
            for found in re.findall(r'"#[0-9A-Fa-f]{3,8}"', text)
            if found.upper() not in ('"#FFFFFF"', '"#000000"')
        ]
    assert not colors, f"цвета мимо токенов: {sorted(set(colors))}"


# ---------- запуск ----------


def test_launcher_opens_qt_by_default_and_tk_on_request(monkeypatch) -> None:
    """Команда medmask одна, а окно выбирается на месте."""
    import medmask.launcher as launcher

    opened: list[str] = []
    monkeypatch.setattr("medmask.gui.main", lambda: opened.append("qt"), raising=False)
    monkeypatch.setattr("medmask.app.main", lambda: opened.append("tk"), raising=False)

    monkeypatch.delenv("MEDMASK_UI", raising=False)
    launcher.main()
    assert opened == ["qt"]

    monkeypatch.setenv("MEDMASK_UI", "tk")
    launcher.main()
    assert opened == ["qt", "tk"]


def test_launcher_falls_back_when_qt_is_missing(monkeypatch) -> None:
    import builtins

    import medmask.launcher as launcher

    opened: list[str] = []
    monkeypatch.setattr("medmask.app.main", lambda: opened.append("tk"), raising=False)
    monkeypatch.delenv("MEDMASK_UI", raising=False)

    real_import = builtins.__import__

    def refuse(name, globals=None, locals=None, fromlist=(), level=0):
        # launcher пишет «from .gui import main»: сюда приходит name="gui"
        # с level=1, а не полное имя пакета.
        if name in ("medmask.gui", "gui") and (level or name.startswith("medmask")):
            raise ImportError("нет PySide6")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", refuse)
    launcher.main()
    assert opened == ["tk"]
