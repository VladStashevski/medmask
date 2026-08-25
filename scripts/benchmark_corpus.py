"""Воспроизводимый локальный benchmark MedMask на каталогах с моковыми данными.

Исходные каталоги копируются во временную область. JSON не содержит исходных
имён файлов, путей или фрагментов медицинского текста.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

try:
    import resource
except ImportError:  # Windows: метрика RSS остаётся нулевой
    resource = None

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from medmask.batch import Progress, process_folder  # noqa: E402


def _peak_rss_mb() -> float:
    if resource is None:
        return 0.0
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS возвращает байты, Linux — KiB.
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return value / divisor


def _process_tree_rss_mb() -> float:
    """Текущая суммарная RSS родителя и всех OCR/text worker-процессов."""
    try:
        completed = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,rss="],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return _peak_rss_mb()

    rows = []
    for line in completed.stdout.splitlines():
        try:
            pid, parent, rss_kib = (int(value) for value in line.split())
        except (ValueError, TypeError):
            continue
        rows.append((pid, parent, rss_kib))

    descendants = {os.getpid()}
    changed = True
    while changed:
        changed = False
        for pid, parent, _rss in rows:
            if parent in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return sum(rss for pid, _parent, rss in rows if pid in descendants) / 1024


def _pdf_metrics(paths: list[Path]) -> tuple[int, int, int, list[str]]:
    page_count = 0
    text_chars = 0
    output_bytes = 0
    text_hashes: list[str] = []
    for path in paths:
        output_bytes += path.stat().st_size
        digest = hashlib.sha256()
        with pymupdf.open(path) as document:
            page_count += document.page_count
            for page in document:
                text = page.get_text("text").replace("\r\n", "\n")
                text_chars += len(text)
                digest.update(text.encode("utf-8"))
        text_hashes.append(digest.hexdigest())
    return page_count, text_chars, output_bytes, text_hashes


def run_case(source: Path, case_dir: Path, label: str) -> dict[str, object]:
    copied_source = case_dir / "source"
    shutil.copytree(source, copied_source)

    stage_seconds: defaultdict[str, float] = defaultdict(float)
    active_stage = "Подготовка"
    stage_started = time.perf_counter()
    peak_tree_rss_mb = _process_tree_rss_mb()
    next_memory_sample = 0.0

    def progress(update: Progress) -> None:
        nonlocal active_stage, stage_started, peak_tree_rss_mb, next_memory_sample
        now = time.perf_counter()
        if now >= next_memory_sample:
            peak_tree_rss_mb = max(peak_tree_rss_mb, _process_tree_rss_mb())
            next_memory_sample = now + 1.0
        if update.stage != active_stage:
            stage_seconds[active_stage] += now - stage_started
            active_stage = update.stage
            stage_started = now

    started = time.perf_counter()
    result = process_folder(copied_source, on_progress=progress)
    finished = time.perf_counter()
    stage_seconds[active_stage] += finished - stage_started

    output_paths = sorted(
        item.output_path for item in result.files if item.output_path is not None
    )
    pages, text_chars, output_bytes, text_hashes = _pdf_metrics(output_paths)
    finding_kinds = Counter(
        kind for item in result.files for kind, _snippet in item.findings
    )

    return {
        "case": label,
        "elapsed_seconds": round(finished - started, 3),
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "peak_process_tree_rss_mb": round(peak_tree_rss_mb, 1),
        "documents": len(result.files),
        "successful": result.successful,
        "failed": result.failed,
        "output_pages": pages,
        "output_text_chars": text_chars,
        "output_bytes": output_bytes,
        "ocr_pages": sum(len(item.ocr_pages) for item in result.files),
        "unrecognized_scan_pages": sum(len(item.scan_pages) for item in result.files),
        "low_confidence_pages": sum(
            len(item.low_confidence_pages) for item in result.files
        ),
        "finding_kinds": dict(sorted(finding_kinds.items())),
        "skipped_by_extension": result.skipped_by_extension,
        "stage_seconds": {
            name: round(seconds, 3)
            for name, seconds in sorted(stage_seconds.items())
        },
        "output_text_sha256": text_hashes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="JSON предыдущего прогона: проверяет эквивалентность результата",
    )
    return parser.parse_args()


_STABLE_FIELDS = (
    "documents",
    "successful",
    "failed",
    "output_pages",
    "output_text_chars",
    "ocr_pages",
    "unrecognized_scan_pages",
    "low_confidence_pages",
    "finding_kinds",
    "skipped_by_extension",
    "output_text_sha256",
)


def compare_reports(baseline: dict, current: dict) -> dict[str, object]:
    baseline_cases = baseline.get("cases", [])
    current_cases = current.get("cases", [])
    cases = []
    equivalent = len(baseline_cases) == len(current_cases)
    for index, current_case in enumerate(current_cases):
        baseline_case = baseline_cases[index] if index < len(baseline_cases) else {}
        mismatches = [
            field
            for field in _STABLE_FIELDS
            if baseline_case.get(field) != current_case.get(field)
        ]
        baseline_seconds = float(baseline_case.get("elapsed_seconds") or 0)
        current_seconds = float(current_case.get("elapsed_seconds") or 0)
        speedup = baseline_seconds / current_seconds if current_seconds else None
        cases.append(
            {
                "case": current_case.get("case", f"case_{index + 1:02d}"),
                "equivalent": not mismatches,
                "mismatched_fields": mismatches,
                "speedup": round(speedup, 3) if speedup is not None else None,
            }
        )
        equivalent = equivalent and not mismatches

    baseline_total = float(baseline.get("total_seconds") or 0)
    current_total = float(current.get("total_seconds") or 0)
    total_speedup = baseline_total / current_total if current_total else None
    return {
        "equivalent": equivalent,
        "total_speedup": round(total_speedup, 3) if total_speedup else None,
        "cases": cases,
    }


def main() -> int:
    args = parse_args()
    for source in args.sources:
        if not source.is_dir():
            raise SystemExit(f"Каталог не найден: {source}")

    work_root = args.work_root or Path(
        tempfile.mkdtemp(prefix="medmask-benchmark-")
    )
    work_root.mkdir(parents=True, exist_ok=True)

    cases = []
    total_started = time.perf_counter()
    for index, source in enumerate(args.sources, start=1):
        case_dir = work_root / f"case_{index:02d}"
        case_dir.mkdir(parents=False, exist_ok=False)
        metrics = run_case(source.resolve(), case_dir, f"case_{index:02d}")
        cases.append(metrics)
        print(
            f"{metrics['case']}: {metrics['elapsed_seconds']} с, "
            f"успешно {metrics['successful']}/{metrics['documents']}, "
            f"OCR-страниц {metrics['ocr_pages']}"
        )

    report: dict[str, object] = {
        "schema_version": 1,
        "work_root": str(work_root),
        "total_seconds": round(time.perf_counter() - total_started, 3),
        "cases": cases,
    }
    exit_code = 0
    if args.baseline is not None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        comparison = compare_reports(baseline, report)
        report["comparison"] = comparison
        exit_code = 0 if comparison["equivalent"] else 2
        status = "совпадает" if comparison["equivalent"] else "ЕСТЬ РАЗЛИЧИЯ"
        print(
            f"Сравнение с baseline: {status}; "
            f"ускорение {comparison['total_speedup']}x"
        )
    report_path = args.json or work_root / "benchmark.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"JSON: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
