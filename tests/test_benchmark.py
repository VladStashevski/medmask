"""Проверки corpus benchmark и строгого сравнения с baseline."""

from __future__ import annotations

from copy import deepcopy

from scripts import benchmark_corpus


def _report(elapsed: float = 10.0) -> dict:
    case = {field: None for field in benchmark_corpus._STABLE_FIELDS}
    case.update(
        {
            "case": "case_01",
            "elapsed_seconds": elapsed,
            "documents": 1,
            "successful": 1,
            "failed": 0,
            "output_pages": 1,
            "output_text_chars": 20,
            "ocr_pages": 1,
            "unrecognized_scan_pages": 0,
            "low_confidence_pages": 0,
            "finding_kinds": {},
            "skipped_by_extension": {},
            "output_text_sha256": ["abc"],
        }
    )
    return {"total_seconds": elapsed, "cases": [case]}


def test_benchmark_comparison_requires_exact_stable_output() -> None:
    baseline = _report(20.0)
    current = _report(10.0)

    comparison = benchmark_corpus.compare_reports(baseline, current)

    assert comparison["equivalent"] is True
    assert comparison["total_speedup"] == 2.0
    assert comparison["cases"][0]["speedup"] == 2.0


def test_benchmark_comparison_reports_hash_mismatch() -> None:
    baseline = _report()
    current = deepcopy(baseline)
    current["cases"][0]["output_text_sha256"] = ["changed"]

    comparison = benchmark_corpus.compare_reports(baseline, current)

    assert comparison["equivalent"] is False
    assert comparison["cases"][0]["mismatched_fields"] == [
        "output_text_sha256"
    ]
