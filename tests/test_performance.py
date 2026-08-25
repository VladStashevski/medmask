"""Инварианты оптимизаций: быстрые пути не должны менять результат или безопасность."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from medmask import batch
from medmask import depersonalizer as engine


class _CountingFont:
    def __init__(self) -> None:
        self.calls = 0

    def text_length(self, value: str, fontsize: float) -> float:
        self.calls += 1
        return len(value) * fontsize


def test_wrap_line_measures_repeated_tokens_once() -> None:
    font = _CountingFont()
    source = " ".join(["диагноз"] * 500)

    wrapped = engine._wrap_line(
        source,
        font,
        fontsize=1.0,
        max_width=79.0,
        width_cache={},
    )

    assert " ".join(wrapped) == source
    assert font.calls == 2  # одно слово и один пробел


@pytest.mark.parametrize(
    ("width", "height", "expected_scale"),
    [
        (595.0, 842.0, engine.OCR_DPI / 72.0),
        (10_000.0, 5_000.0, engine.local_ocr.MAX_IMAGE_SIDE / 10_000.0),
    ],
)
def test_ocr_render_is_capped_before_inference(
    monkeypatch, width: float, height: float, expected_scale: float
) -> None:
    seen = {}
    recognized = engine.local_ocr.OCRResult(
        text="тест",
        confidence=1.0,
        line_count=1,
    )

    class Page:
        rect = engine.fitz.Rect(0, 0, width, height)

        def get_pixmap(self, **kwargs):
            seen.update(kwargs)
            return object()

    monkeypatch.setattr(
        engine.local_ocr,
        "recognize_pixmap",
        lambda pixmap: recognized,
    )

    assert engine._ocr_page(Page()) is recognized
    assert seen["matrix"].a == pytest.approx(expected_scale)
    assert seen["matrix"].d == pytest.approx(expected_scale)


def test_depersonalize_context_is_isolated_between_threads(monkeypatch) -> None:
    barrier = threading.Barrier(2)
    observed: list[bool] = []

    def fake_depersonalize(text, memory, sweep):
        barrier.wait(timeout=2)
        observed.append(engine._MEM.get() is memory)
        barrier.wait(timeout=2)
        return text

    monkeypatch.setattr(engine, "_depersonalize", fake_depersonalize)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(engine.depersonalize, ["первый", "второй"]))

    assert results == ["первый", "второй"]
    assert observed == [True, True]
    assert engine._MEM.get() is None


def test_depersonalize_context_is_reset_after_error(monkeypatch) -> None:
    def fail(text, memory, sweep):
        raise RuntimeError("test error")

    monkeypatch.setattr(engine, "_depersonalize", fail)

    with pytest.raises(RuntimeError, match="test error"):
        engine.depersonalize("тест")

    assert engine._MEM.get() is None


def test_parallel_worker_limit_accounts_for_cpu_and_memory(monkeypatch) -> None:
    monkeypatch.setattr(batch.os, "cpu_count", lambda: 10)
    monkeypatch.setattr(batch, "_physical_memory_bytes", lambda: 16 * 1024**3)

    assert batch._worker_limits(ocr_jobs=20, text_jobs=20) == (2, 2)

    monkeypatch.setattr(batch, "_physical_memory_bytes", lambda: 8 * 1024**3)
    assert batch._worker_limits(ocr_jobs=20, text_jobs=20) == (1, 4)


def test_parallel_progress_uses_aggregate_fraction() -> None:
    progress = batch.Progress(
        completed=1,
        total=10,
        current_name="document.pdf",
        file_fraction=0.9,
        overall_fraction=0.42,
    )

    assert progress.percent == 42

