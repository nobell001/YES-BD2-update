"""Traditional -> Simplified conversion for OCR text comparisons."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _converter():
    try:
        import opencc
    except ImportError:
        return None
    return opencc.OpenCC("t2s")


def to_simplified(text: str) -> str:
    converter = _converter()
    return converter.convert(str(text)) if converter is not None else str(text)
