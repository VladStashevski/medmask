"""Полностью локальное OCR для сканов и изображений.

Все модели находятся в ``medmask/assets`` и перед первым использованием
проверяются по SHA-256.  Явные пути к моделям не дают RapidOCR обращаться в
сеть: готовая программа работает одинаково в macOS и Windows без Python и
без системного Tesseract.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any


ASSET_DIR = Path(__file__).resolve().parent / "assets"
MODEL_HASHES = {
    "PP-OCRv6_det_small.onnx": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    "cyrillic_PP-OCRv5_rec_mobile.onnx": "90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711",
}


class OCRError(RuntimeError):
    """OCR нельзя безопасно выполнить."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float
    line_count: int

    @property
    def low_confidence(self) -> bool:
        return bool(self.text) and self.confidence < 0.65


_engine: Any | None = None
_engine_lock = Lock()
_assets_verified = False


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets() -> None:
    """Проверяет наличие и целостность встроенных моделей без сетевых запросов."""
    global _assets_verified
    if _assets_verified:
        return

    missing = [name for name in MODEL_HASHES if not (ASSET_DIR / name).is_file()]
    if missing:
        raise OCRError("в сборке отсутствует локальная OCR-модель")

    damaged = [
        name
        for name, expected in MODEL_HASHES.items()
        if _file_sha256(ASSET_DIR / name) != expected
    ]
    if damaged:
        raise OCRError("локальная OCR-модель повреждена")
    _assets_verified = True


def _get_engine():
    global _engine
    if _engine is not None:
        return _engine

    with _engine_lock:
        if _engine is not None:
            return _engine
        verify_assets()
        try:
            from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR

            _engine = RapidOCR(
                params={
                    "Global.log_level": "error",
                    "Global.text_score": 0.35,
                    "Global.max_side_len": 2200,
                    "Det.engine_type": EngineType.ONNXRUNTIME,
                    "Det.model_type": ModelType.SMALL,
                    "Det.ocr_version": OCRVersion.PPOCRV6,
                    "Det.model_path": str(ASSET_DIR / "PP-OCRv6_det_small.onnx"),
                    "Cls.engine_type": EngineType.ONNXRUNTIME,
                    "Cls.model_type": ModelType.MOBILE,
                    "Cls.ocr_version": OCRVersion.PPOCRV4,
                    "Cls.model_path": str(
                        ASSET_DIR / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
                    ),
                    "Rec.engine_type": EngineType.ONNXRUNTIME,
                    "Rec.lang_type": LangRec.CYRILLIC,
                    "Rec.model_type": ModelType.MOBILE,
                    "Rec.ocr_version": OCRVersion.PPOCRV5,
                    "Rec.model_path": str(
                        ASSET_DIR / "cyrillic_PP-OCRv5_rec_mobile.onnx"
                    ),
                }
            )
        except OCRError:
            raise
        except Exception as error:
            raise OCRError("не удалось запустить локальный OCR") from error
    return _engine


def _box_metrics(box: Any) -> tuple[float, float, float, float]:
    points = list(box)
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    top, bottom = min(ys), max(ys)
    return min(xs), top, max(1.0, bottom - top), (top + bottom) / 2


def _restore_reading_order(texts: list[str], boxes: Any) -> list[str]:
    """Объединяет OCR-фрагменты в строки сверху вниз и слева направо."""
    if boxes is None or len(boxes) != len(texts):
        return [text.strip() for text in texts if text.strip()]

    items = []
    for text, box in zip(texts, boxes):
        clean = text.strip()
        if not clean:
            continue
        left, top, height, center = _box_metrics(box)
        items.append((top, left, height, center, clean))
    items.sort(key=lambda item: (item[0], item[1]))

    rows: list[list[tuple[float, float, float, float, str]]] = []
    for item in items:
        if not rows:
            rows.append([item])
            continue
        row = rows[-1]
        row_center = sum(value[3] for value in row) / len(row)
        tolerance = max(8.0, min(item[2], max(value[2] for value in row)) * 0.6)
        if abs(item[3] - row_center) <= tolerance:
            row.append(item)
        else:
            rows.append([item])

    output = []
    for row in rows:
        row.sort(key=lambda item: item[1])
        output.append("  ".join(item[4] for item in row))
    return output


def recognize(image: Any) -> OCRResult:
    """Распознаёт RGB-массив изображения и возвращает обычный локальный текст."""
    try:
        result = _get_engine()(image)
    except OCRError:
        raise
    except Exception as error:
        raise OCRError("ошибка распознавания изображения") from error

    texts = list(result.txts or [])
    scores = [float(score) for score in (result.scores or [])]
    lines = _restore_reading_order(texts, result.boxes)
    confidence = sum(scores) / len(scores) if scores else 0.0
    return OCRResult(
        text="\n".join(lines),
        confidence=confidence,
        line_count=len(lines),
    )


def recognize_pixmap(pixmap: Any) -> OCRResult:
    """Распознаёт ``pymupdf.Pixmap`` без временных файлов."""
    try:
        import numpy as np

        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        if pixmap.n == 4:
            image = image[:, :, :3]
        return recognize(image)
    except OCRError:
        raise
    except Exception as error:
        raise OCRError("не удалось подготовить страницу для OCR") from error
