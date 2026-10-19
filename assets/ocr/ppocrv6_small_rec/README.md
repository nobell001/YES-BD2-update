# PP-OCRv6 small text recognizer

Used by `src/compat/ocr_models.py`: onnxocr keeps finding text with its own
PP-OCRv5 mobile detector and reads each found box with this recognizer.

- `rec.onnx` sha256 `5435fd747c9e0efe15a96d0b378d5bd157e9492ed8fd80edf08f30d02fa24634`
- `ppocrv6_dict.txt` sha256 `769e7fa79bb297b5f18d8dbd149e364a45bc61f2b3f574e5ea836f0b261c23a6`
- Source: `onnxocr/models/ppocrv6/small/` in the onnxocr 4.0.0 wheel on PyPI
  (https://github.com/jingsongliujing/OnnxOCR), Apache-2.0; the model itself
  is PaddleOCR's PP-OCRv6 small recognizer (Apache-2.0).
