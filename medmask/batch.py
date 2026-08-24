"""Пакетная обработка папки без сети и без изменения исходных файлов."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import depersonalizer as engine


OUTPUT_FOLDER_NAME = "Обезличенные"
REPORT_FILE_NAME = "_ОТЧЁТ.txt"


class MedMaskError(RuntimeError):
    """Понятная пользователю ошибка обработки."""


@dataclass(frozen=True)
class Progress:
    completed: int
    total: int
    current_name: str

    @property
    def percent(self) -> int:
        if self.total == 0:
            return 0
        return round(self.completed * 100 / self.total)


@dataclass
class FileResult:
    number: int
    source_path: Path
    output_path: Path | None = None
    scan_pages: list[int] = field(default_factory=list)
    image_pages: list[int] = field(default_factory=list)
    findings: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def code(self) -> str:
        return f"document_{self.number:04d}"

    @property
    def needs_review(self) -> bool:
        return bool(self.scan_pages or self.findings or self.error)


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


ProgressCallback = Callable[[Progress], None]


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
    message = str(error).lower()
    if "password" in message or "encrypted" in message:
        return "документ защищён паролем"
    if "cannot open" in message or "invalid" in message or "format" in message:
        return "не удалось прочитать формат документа"
    return f"ошибка обработки ({type(error).__name__})"


def _process_file(path: Path, number: int, output_dir: Path) -> FileResult:
    result = FileResult(number=number, source_path=path)
    output_path = output_dir / f"{result.code}.pdf"

    try:
        if path.suffix.lower() == ".pdf":
            page_texts, page_rects, scan_pages, image_pages = engine.build_pages_from_pdf(str(path))
            result.scan_pages = scan_pages
            result.image_pages = image_pages
        else:
            raw_text = engine.READERS[path.suffix.lower()](str(path))
            page_texts, page_rects = engine.build_pages_from_text(raw_text)

        engine.save_clean_pdf(page_texts, page_rects, str(output_path))
        result.output_path = output_path
        result.findings = engine.audit_pdf(str(output_path))
    except Exception as error:
        result.error = _safe_error(error)
        if output_path.exists():
            output_path.unlink()

    return result


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
    lines = [
        "ОТЧЁТ MEDMASK",
        f"Дата: {datetime.now():%Y-%m-%d %H:%M}",
        f"Найдено поддерживаемых документов: {len(files)}",
        f"Создано обезличенных PDF: {successful}",
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
                f"{item.code}: страницы без извлекаемого текста "
                f"({_format_numbers(item.scan_pages)}); содержимое сканов не перенесено."
            )
        if item.image_pages:
            warnings.append(
                f"{item.code}: изображения удалены со страниц "
                f"({_format_numbers(item.image_pages)})."
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
                "Изображения JPG/PNG и сканы требуют отдельного OCR.",
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
) -> BatchResult:
    source = Path(source_dir).expanduser().resolve()
    if not source.is_dir():
        raise MedMaskError("Выбранная папка не существует.")
    if engine.fitz is None:
        raise MedMaskError("В сборке отсутствует модуль обработки PDF.")
    if engine._find_cyrillic_font() is None:
        raise MedMaskError("На компьютере не найден шрифт с поддержкой кириллицы.")

    files, skipped = discover_files(source)
    if not files:
        formats = ", ".join(sorted(engine.SUPPORTED_EXT))
        raise MedMaskError(f"В папке нет поддерживаемых документов ({formats}).")

    output_dir = _new_output_dir(source)
    output_dir.mkdir(parents=False, exist_ok=False)

    results: list[FileResult] = []
    total = len(files)
    for number, path in enumerate(files, start=1):
        if on_progress:
            on_progress(Progress(number - 1, total, path.name))
        results.append(_process_file(path, number, output_dir))
        if on_progress:
            on_progress(Progress(number, total, path.name))

    report_path = write_safe_report(output_dir, results, skipped)
    return BatchResult(
        source_dir=source,
        output_dir=output_dir,
        files=results,
        skipped_by_extension=skipped,
        report_path=report_path,
    )
