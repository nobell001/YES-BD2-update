"""Read text with the PP-OCRv6 small recognizer, keep the PP-OCRv5 detector.

ok-script builds onnxocr with only use_openvino/use_npu, so onnxocr would load
the PP-OCRv5 models bundled with onnxocr-ppocrv5 0.0.22.  Measured 2026-10-19
on the test frames (3518 tests, 160 real frames):
- v6 small recognizer: reads 繁中 UI text and small titles better; every test
  that passes with v5 still passes; the same speed per box as v5.
- v6 small detector: finds far fewer small numbers on a full screen (bag grid
  113 boxes → 14) and is ~25% slower per small box, so it is not used.
"""

from __future__ import annotations

from pathlib import Path

RECOGNIZER_DIR = Path(__file__).resolve().parents[2] / "assets" / "ocr" / "ppocrv6_small_rec"
RECOGNIZER_MODEL = RECOGNIZER_DIR / "rec.onnx"
RECOGNIZER_DICT = RECOGNIZER_DIR / "ppocrv6_dict.txt"
_PATCH_MARKER = "_ok_bd2_v6_recognizer"


def patch_ocr_class(ocr_class: type) -> None:
    """Default every new onnxocr engine to the v6 recognizer and its dictionary.

    Callers that pass their own rec_model_dir keep it.  When the files are
    missing (broken install) onnxocr keeps its bundled v5 recognizer."""

    if getattr(ocr_class, _PATCH_MARKER, False):
        return
    original_init = ocr_class.__init__

    def init_with_v6_recognizer(self, *args, **kwargs):
        if (
            "rec_model_dir" not in kwargs
            and RECOGNIZER_MODEL.is_file()
            and RECOGNIZER_DICT.is_file()
        ):
            kwargs["rec_model_dir"] = str(RECOGNIZER_MODEL)
            kwargs["rec_char_dict_path"] = str(RECOGNIZER_DICT)
        original_init(self, *args, **kwargs)

    ocr_class.__init__ = init_with_v6_recognizer
    setattr(ocr_class, _PATCH_MARKER, True)


def install_v6_recognizer() -> None:
    try:
        from onnxocr.onnx_paddleocr import ONNXPaddleOcr
    except Exception:  # dependency_guard reports a missing onnxocr; never block import
        return
    patch_ocr_class(ONNXPaddleOcr)
