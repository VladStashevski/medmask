"""Пакетная обработка папки без сети и без изменения исходных файлов."""

from __future__ import annotations

import concurrent.futures
import multiprocessing
import os
import queue
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import OUTPUT_FOLDER_NAME
from . import depersonalizer as engine


REPORT_FILE_NAME = "_ОТЧЁТ.txt"


class MedMaskError(RuntimeError):
    """Понятная пользователю ошибка обработки."""


class BatchCancelled(MedMaskError):
    """Пользователь отменил пакет до его завершения."""


@dataclass(frozen=True)
class Progress:
    completed: int
    total: int
    current_name: str
    stage: str = "Подготовка документа"
    detail: str = ""
    file_fraction: float = 0.0
    # В параллельном режиме несколько файлов движутся одновременно, поэтому
    # completed + file_fraction уже не описывает общий прогресс.
    overall_fraction: float | None = None
    # Номер документа в списке (1-based) и его исход. Окно держит строку на
    # каждый файл и обновляет ее по номеру: при параллельной обработке имена
    # приходят вперемешку, а номер остается единственным надежным ключом.
    number: int = 0
    outcome: str = ""
    badge: str = ""

    @property
    def percent(self) -> int:
        if self.overall_fraction is not None:
            return min(100, max(0, round(self.overall_fraction * 100)))
        if self.total == 0:
            return 0
        fraction = min(1.0, max(0.0, self.file_fraction))
        value = round((self.completed + fraction) * 100 / self.total)
        if self.completed < self.total and fraction > 0:
            return max(1, min(99, value))
        return min(100, max(0, value))


@dataclass
class FileResult:
    number: int
    source_path: Path
    output_path: Path | None = None
    scan_pages: list[int] = field(default_factory=list)
    image_pages: list[int] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    low_confidence_pages: list[int] = field(default_factory=list)
    findings: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def code(self) -> str:
        return f"document_{self.number:04d}"

    @property
    def needs_review(self) -> bool:
        return bool(
            self.scan_pages
            or self.ocr_pages
            or self.low_confidence_pages
            or self.findings
            or self.error
        )


def outcome_of(result: "FileResult") -> str:
    """Как строка документа выглядит в списке: ошибка, требует взгляда, готово.

    Отличается от BatchResult.needs_review намеренно: там распознанный скан
    сам по себе повод перечитать результат, а в списке OCR — это пометка на
    строке, а не желтый статус на весь документ.
    """
    if result.error is not None:
        return "failed"
    if result.low_confidence_pages or result.findings or result.scan_pages:
        return "review"
    return "done"


def badge_of(result: "FileResult") -> str:
    """Короткая пометка справа в строке."""
    marks: list[str] = []
    if result.ocr_pages:
        marks.append("OCR")
    if result.low_confidence_pages or result.findings:
        marks.append("проверить")
    return "  ·  ".join(marks)


@dataclass
class BatchResult:
    source_dir: Path
    output_dir: Path
    files: list[FileResult]
    skipped_by_extension: dict[str, int]
    report_path: Path

    @property
    def successful(self) -> int:
        return sum(item.output_path is not None for item in self.files)

    @property
    def failed(self) -> int:
        return sum(item.error is not None for item in self.files)

    @property
    def needs_review(self) -> list[FileResult]:
        return [item for item in self.files if item.needs_review]

    @property
    def recognized_with_ocr(self) -> int:
        return sum(bool(item.ocr_pages) for item in self.files)


ProgressCallback = Callable[[Progress], None]
FileProgressCallback = Callable[[str, float, str], None]


def _hidden_or_temporary(relative_path: Path) -> bool:
    return any(part.startswith(".") for part in relative_path.parts) or engine.should_skip_filename(
        relative_path.name
    )


def discover_files(source_dir: Path) -> tuple[list[Path], dict[str, int]]:
    supported: list[Path] = []
    skipped: Counter[str] = Counter()
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir)
        if _hidden_or_temporary(relative):
            continue
        extension = path.suffix.lower()
        if extension in engine.SUPPORTED_EXT:
            supported.append(path)
        else:
            skipped[extension or "без расширения"] += 1
    supported.sort(key=lambda item: str(item.relative_to(source_dir)).casefold())
    return supported, dict(sorted(skipped.items()))


def _requires_ocr(path: Path) -> bool:
    """Предварительно отделяет тяжёлые OCR-задания от текстовых.

    Ошибка чтения не должна ломать подготовку очереди: сам обработчик позже
    превратит её в безопасную ошибку конкретного документа.
    """
    extension = path.suffix.lower()
    if extension in engine.IMAGE_EXT:
        return True
    if extension != ".pdf" or engine.fitz is None:
        return False
    try:
        with engine.fitz.open(path) as document:
            for page in document:
                raw = page.get_text("text", sort=True)
                images = page.get_images(full=True)
                if engine._needs_ocr(page, raw, bool(images)):
                    return True
    except Exception:
        return False
    return False


def _physical_memory_bytes() -> int:
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError, ValueError):
            return 0
    try:
        pages = int(os.sysconf("SC_PHYS_PAGES"))
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return max(0, pages * page_size)
    except (AttributeError, OSError, ValueError):
        return 0


def _worker_limits(ocr_jobs: int, text_jobs: int) -> tuple[int, int]:
    """Выбирает пределы без переподписки CPU и без взрыва памяти OCR."""
    cpu_count = max(1, os.cpu_count() or 1)
    memory = _physical_memory_bytes()
    enough_for_two_ocr = memory >= 12 * 1024**3 and cpu_count >= 8
    ocr_workers = min(ocr_jobs, 2 if enough_for_two_ocr else 1)
    reserved_for_ocr = ocr_workers * min(4, cpu_count)
    text_capacity = max(1, cpu_count - reserved_for_ocr)
    text_workers = min(text_jobs, 4, text_capacity)
    return ocr_workers, text_workers


def _new_output_dir(source_dir: Path, now: datetime | None = None) -> Path:
    parent = source_dir.parent
    first = parent / OUTPUT_FOLDER_NAME
    if not first.exists():
        return first

    stamp = (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    candidate = parent / f"{OUTPUT_FOLDER_NAME}_{stamp}"
    counter = 2
    while candidate.exists():
        candidate = parent / f"{OUTPUT_FOLDER_NAME}_{stamp}_{counter}"
        counter += 1
    return candidate


def _safe_error(error: Exception) -> str:
    """Не переносит путь или исходное имя файла в отдаваемый отчёт."""
    if isinstance(error, PermissionError):
        return "нет доступа к файлу"
    if isinstance(error, FileNotFoundError):
        return "файл недоступен"
    if isinstance(error, engine.zipfile.BadZipFile):
        return "повреждённый офисный документ"
    if isinstance(error, engine.local_ocr.OCRError):
        return str(error)
    message = str(error).lower()
    if "password" in message or "encrypted" in message:
        return "документ защищён паролем"
    if "cannot open" in message or "invalid" in message or "format" in message:
        return "не удалось прочитать формат документа"
    return f"ошибка обработки ({type(error).__name__})"


_ENGINE_PHASES = {
    "ocr": ("Распознавание скана", 0.05, 0.48, "Страница"),
    "anonymize": ("Извлечение и обезличивание", 0.05, 0.48, "Страница"),
    "finalize": ("Финальная обработка текста", 0.54, 0.10, "Страница"),
    "render": ("Создание нового PDF", 0.66, 0.21, "Фрагмент"),
    "audit": ("Проверка результата", 0.89, 0.09, "Страница"),
}


def _process_file(
    path: Path,
    number: int,
    output_dir: Path,
    on_stage: FileProgressCallback | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> FileResult:
    result = FileResult(number=number, source_path=path)
    output_path = output_dir / f"{result.code}.pdf"

    def notify(stage: str, fraction: float, detail: str = "") -> None:
        if is_cancelled is not None and is_cancelled():
            raise BatchCancelled("Обработка отменена.")
        if on_stage:
            on_stage(stage, fraction, detail)

    def engine_progress(phase: str, completed: int, total: int) -> None:
        stage, start, span, unit = _ENGINE_PHASES[phase]
        ratio = completed / total if total else 1.0
        notify(stage, start + span * ratio, f"{unit} {completed} из {total}")

    try:
        notify("Чтение документа", 0.02)
        if path.suffix.lower() == ".pdf":
            (
                page_texts,
                page_rects,
                scan_pages,
                image_pages,
                ocr_pages,
                low_confidence_pages,
            ) = engine.build_pages_from_pdf(str(path), on_progress=engine_progress)
            result.scan_pages = scan_pages
            result.image_pages = image_pages
            result.ocr_pages = ocr_pages
            result.low_confidence_pages = low_confidence_pages
        elif path.suffix.lower() in engine.IMAGE_EXT:
            (
                page_texts,
                page_rects,
                scan_pages,
                ocr_pages,
                low_confidence_pages,
            ) = engine.build_pages_from_image(str(path), on_progress=engine_progress)
            result.scan_pages = scan_pages
            result.image_pages = list(range(1, len(page_texts) + 1))
            result.ocr_pages = ocr_pages
            result.low_confidence_pages = low_confidence_pages
        else:
            raw_text = engine.READERS[path.suffix.lower()](str(path))
            notify("Обезличивание текста", 0.20)
            page_texts, page_rects = engine.build_pages_from_text(
                raw_text,
                source_name=str(path),
            )
            notify("Текст обезличен", 0.62)

        notify("Создание нового PDF", 0.65)
        engine.save_clean_pdf(
            page_texts,
            page_rects,
            str(output_path),
            on_progress=engine_progress,
        )
        result.output_path = output_path
        notify("Проверка результата", 0.88)
        result.findings = engine.audit_pdf(str(output_path), on_progress=engine_progress)
        notify("Документ готов", 0.99)
    except BatchCancelled:
        if output_path.exists():
            output_path.unlink()
        raise
    except Exception as error:
        result.error = _safe_error(error)
        if output_path.exists():
            output_path.unlink()

    return result


_WORKER_PROGRESS_QUEUE = None
_WORKER_CANCEL_EVENT = None


def _init_worker(progress_queue, cancel_event) -> None:
    global _WORKER_PROGRESS_QUEUE, _WORKER_CANCEL_EVENT
    _WORKER_PROGRESS_QUEUE = progress_queue
    _WORKER_CANCEL_EVENT = cancel_event


def _worker_process_file(path: Path, number: int, output_dir: Path) -> FileResult:
    def report(stage: str, fraction: float, detail: str) -> None:
        if _WORKER_PROGRESS_QUEUE is not None:
            _WORKER_PROGRESS_QUEUE.put((number, stage, fraction, detail))

    def cancelled() -> bool:
        return bool(
            _WORKER_CANCEL_EVENT is not None and _WORKER_CANCEL_EVENT.is_set()
        )

    return _process_file(
        path,
        number,
        output_dir,
        on_stage=report,
        is_cancelled=cancelled,
    )


def _process_files_parallel(
    files: list[Path],
    output_dir: Path,
    requires_ocr: list[bool],
    on_progress: ProgressCallback | None,
    is_cancelled: Callable[[], bool] | None,
) -> list[FileResult]:
    """Запускает отдельные ограниченные пулы для OCR и текстовых заданий."""
    context = multiprocessing.get_context("spawn")
    progress_queue = context.Queue()
    cancel_event = context.Event()
    numbered = list(enumerate(files, start=1))
    ocr_jobs = [item for item, flag in zip(numbered, requires_ocr) if flag]
    text_jobs = [item for item, flag in zip(numbered, requires_ocr) if not flag]
    ocr_workers, text_workers = _worker_limits(len(ocr_jobs), len(text_jobs))

    fractions = {number: 0.0 for number, _path in numbered}
    results: dict[int, FileResult] = {}
    future_info: dict[concurrent.futures.Future, tuple[int, Path]] = {}
    executors: list[concurrent.futures.ProcessPoolExecutor] = []
    total = len(files)

    def emit(
        number: int,
        stage: str,
        fraction: float,
        detail: str = "",
        outcome: str = "",
        badge: str = "",
    ) -> None:
        fractions[number] = max(fractions[number], min(1.0, max(0.0, fraction)))
        if on_progress is None:
            return
        overall = sum(fractions.values()) / total if total else 0.0
        on_progress(
            Progress(
                completed=len(results),
                total=total,
                current_name=files[number - 1].name,
                stage=stage,
                detail=detail,
                file_fraction=fractions[number],
                overall_fraction=overall,
                number=number,
                outcome=outcome,
                badge=badge,
            )
        )

    def drain_progress() -> None:
        while True:
            try:
                number, stage, fraction, detail = progress_queue.get_nowait()
            except queue.Empty:
                return
            emit(number, stage, fraction, detail)

    def add_pool(
        jobs: list[tuple[int, Path]], workers: int
    ) -> concurrent.futures.ProcessPoolExecutor | None:
        if not jobs or workers <= 0:
            return None
        executor = concurrent.futures.ProcessPoolExecutor(
            max_workers=workers,
            mp_context=context,
            initializer=_init_worker,
            initargs=(progress_queue, cancel_event),
        )
        executors.append(executor)
        for number, path in jobs:
            future = executor.submit(_worker_process_file, path, number, output_dir)
            future_info[future] = (number, path)
        return executor

    cancelled = False
    try:
        add_pool(ocr_jobs, ocr_workers)
        add_pool(text_jobs, text_workers)
        pending = set(future_info)
        while pending:
            drain_progress()
            if is_cancelled is not None and is_cancelled():
                cancelled = True
                cancel_event.set()
                for future in pending:
                    future.cancel()
                raise BatchCancelled("Обработка отменена.")

            done, pending = concurrent.futures.wait(
                pending,
                timeout=0.05,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                number, path = future_info[future]
                try:
                    result = future.result()
                except BatchCancelled:
                    cancelled = True
                    cancel_event.set()
                    raise
                except Exception as error:  # noqa: BLE001 — изоляция worker-сбоя
                    result = FileResult(
                        number=number,
                        source_path=path,
                        error=_safe_error(error),
                    )
                results[number] = result
                emit(
                    number,
                    "Документ готов" if result.error is None else "Ошибка документа",
                    1.0,
                    outcome=outcome_of(result),
                    badge=badge_of(result),
                )
        drain_progress()
    except BaseException:
        cancel_event.set()
        raise
    finally:
        for executor in executors:
            executor.shutdown(wait=True, cancel_futures=cancelled)
        progress_queue.close()
        progress_queue.join_thread()

    return [results[number] for number in range(1, total + 1)]


def _format_numbers(values: list[int]) -> str:
    return ", ".join(str(value) for value in values)


def write_safe_report(
    output_dir: Path,
    files: list[FileResult],
    skipped_by_extension: dict[str, int],
) -> Path:
    """Пишет отчёт без исходных имён, путей и фрагментов медицинского текста."""
    successful = sum(item.output_path is not None for item in files)
    failed = sum(item.error is not None for item in files)
    ocr_documents = sum(bool(item.ocr_pages) for item in files)
    ocr_pages = sum(len(item.ocr_pages) for item in files)
    lines = [
        "ОТЧЁТ MEDMASK",
        f"Дата: {datetime.now():%Y-%m-%d %H:%M}",
        f"Найдено поддерживаемых документов: {len(files)}",
        f"Создано обезличенных PDF: {successful}",
        f"OCR применён: документов {ocr_documents}, страниц {ocr_pages}",
        f"Ошибок: {failed}",
        "",
        "Исходные имена файлов и фрагменты документов намеренно не записываются.",
        "",
    ]

    warnings: list[str] = []
    for item in files:
        if item.error:
            warnings.append(f"{item.code}: {item.error}.")
        if item.scan_pages:
            warnings.append(
                f"{item.code}: OCR не распознал текст на страницах "
                f"({_format_numbers(item.scan_pages)})."
            )
        if item.ocr_pages:
            warnings.append(
                f"{item.code}: OCR применён на страницах "
                f"({_format_numbers(item.ocr_pages)}); результат нужно просмотреть."
            )
        if item.low_confidence_pages:
            warnings.append(
                f"{item.code}: низкая уверенность OCR на страницах "
                f"({_format_numbers(item.low_confidence_pages)})."
            )
        removed_only = sorted(set(item.image_pages) - set(item.ocr_pages) - set(item.scan_pages))
        if removed_only:
            warnings.append(
                f"{item.code}: изображения удалены со страниц "
                f"({_format_numbers(removed_only)})."
            )
        if item.findings:
            kinds = ", ".join(sorted({kind for kind, _ in item.findings}))
            warnings.append(
                f"{item.code}: автоматическая проверка нашла возможные остаточные данные ({kinds})."
            )

    if warnings:
        lines.extend(["ТРЕБУЕТСЯ ПРОВЕРКА:", *[f"- {warning}" for warning in warnings], ""])
    else:
        lines.extend(["Автоматическая проверка не нашла предупреждений.", ""])

    if skipped_by_extension:
        skipped = ", ".join(
            f"{extension}: {count}" for extension, count in skipped_by_extension.items()
        )
        lines.extend(
            [
                f"Неподдерживаемые файлы не обрабатывались: {skipped}.",
                "",
            ]
        )

    lines.extend(
        [
            "ВАЖНО: автоматическое обезличивание не даёт абсолютной гарантии.",
            "Перед передачей документов обязательно просмотрите итоговые PDF.",
        ]
    )

    report_path = output_dir / REPORT_FILE_NAME
    report_path.write_text("\n".join(lines), encoding="utf-8-sig")
    return report_path


def process_folder(
    source_dir: str | Path,
    on_progress: ProgressCallback | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    discovered: tuple[list[Path], dict[str, int]] | None = None,
) -> BatchResult:
    source = Path(source_dir).expanduser().resolve()
    if not source.is_dir():
        raise MedMaskError("Выбранная папка не существует.")
    if engine.fitz is None:
        raise MedMaskError("В сборке отсутствует модуль обработки PDF.")
    if engine._find_cyrillic_font() is None:
        raise MedMaskError("На компьютере не найден шрифт с поддержкой кириллицы.")

    if discovered is None:
        files, skipped = discover_files(source)
    else:
        manifest_files, manifest_skipped = discovered
        files = [path for path in manifest_files if path.is_file()]
        skipped = dict(manifest_skipped)
    if not files:
        formats = ", ".join(sorted(engine.SUPPORTED_EXT))
        raise MedMaskError(f"В папке нет поддерживаемых документов ({formats}).")

    total = len(files)
    use_parallel = (
        total >= 4 and os.environ.get("MEDMASK_DISABLE_PARALLEL", "") != "1"
    )
    requires_ocr: list[bool] = []
    if use_parallel:
        for number, path in enumerate(files, start=1):
            if is_cancelled is not None and is_cancelled():
                raise BatchCancelled("Обработка отменена.")
            if on_progress:
                on_progress(
                    Progress(
                        completed=0,
                        total=total,
                        current_name=path.name,
                        stage="Анализ документов",
                        detail=f"Файл {number} из {total}",
                    )
                )
            requires_ocr.append(_requires_ocr(path))

    if is_cancelled is not None and is_cancelled():
        raise BatchCancelled("Обработка отменена.")

    output_dir = _new_output_dir(source)
    output_dir.mkdir(parents=False, exist_ok=False)

    try:
        if use_parallel:
            results = _process_files_parallel(
                files,
                output_dir,
                requires_ocr,
                on_progress,
                is_cancelled,
            )
        else:
            results = []
            for number, path in enumerate(files, start=1):
                def report_stage(
                    stage: str,
                    fraction: float,
                    detail: str,
                    outcome: str = "",
                    badge: str = "",
                    number: int = number,
                    path: Path = path,
                ) -> None:
                    if on_progress:
                        on_progress(
                            Progress(
                                completed=number - 1,
                                total=total,
                                current_name=path.name,
                                stage=stage,
                                detail=detail,
                                file_fraction=fraction,
                                number=number,
                                outcome=outcome,
                                badge=badge,
                            )
                        )

                file_result = _process_file(
                    path,
                    number,
                    output_dir,
                    on_stage=report_stage,
                    is_cancelled=is_cancelled,
                )
                results.append(file_result)
                report_stage(
                    "Документ готов" if file_result.error is None else "Ошибка документа",
                    1.0,
                    "",
                    outcome_of(file_result),
                    badge_of(file_result),
                )
        if is_cancelled is not None and is_cancelled():
            raise BatchCancelled("Обработка отменена.")
        report_path = write_safe_report(output_dir, results, skipped)
    except BaseException:
        # Каталог создан этим запуском и имеет уникальное имя. Частичный набор
        # без итогового отчёта нельзя принять за завершённый результат.
        shutil.rmtree(output_dir, ignore_errors=True)
        raise

    return BatchResult(
        source_dir=source,
        output_dir=output_dir,
        files=results,
        skipped_by_extension=skipped,
        report_path=report_path,
    )
