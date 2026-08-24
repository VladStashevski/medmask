"""Минимальный PyInstaller hook для используемого ONNX-варианта RapidOCR."""

from PyInstaller.utils.hooks import collect_data_files


datas = collect_data_files(
    "rapidocr",
    includes=["config.yaml", "default_models.yaml"],
)

hiddenimports = [
    "rapidocr.main",
    "rapidocr.inference_engine.onnxruntime",
]
