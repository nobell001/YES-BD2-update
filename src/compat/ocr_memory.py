"""Keep the OCR's memory bounded.

onnxocr compiles its OpenVINO models for CPU with a fully dynamic input
shape.  The CPU plugin then keeps compiled kernels for every new input size it
sees, up to CPU_RUNTIME_CACHE_CAPACITY entries (default 5000), and never frees
them.  The tool reads text from regions of many different sizes, so the cache
kept growing: Leo's 4K test run 2026-10-05 went from 1.4 GB to 9.6 GB private
memory in one daily, and stayed there while idle.

Measured with random crop sizes (cloud, 400 OCR calls): no cap 187 -> 1932 MB,
cap 50 -> 790 MB, cap 0 -> 721 MB.  On Leo's 4K PC (240 crops) no cap went
past 5.7 GB, cap 100 levelled off near 2.0 GB.  With the same 12 sizes
repeated, cap 100 cost ~5 ms per OCR call against no cap, cap 0 ~8 ms.
Recognition itself is unchanged; only re-used kernels are dropped sooner.
"""

from __future__ import annotations

from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

CPU_RUNTIME_CACHE_CAPACITY = 100
CACHE_CAPACITY_KEY = "CPU_RUNTIME_CACHE_CAPACITY"
_PATCH_MARKER = "_ok_bd2_runtime_cache_capped"


def _is_cpu(device_name: object) -> bool:
    return isinstance(device_name, str) and device_name.upper().startswith("CPU")


def patch_core_compile_model(core_class: type) -> None:
    """Add the cache cap to every CPU compile that doesn't set its own."""

    if getattr(core_class, _PATCH_MARKER, False):
        return
    original_compile_model = core_class.compile_model

    def capped_compile_model(self, model, device_name=None, config=None, *args, **kwargs):
        if _is_cpu(device_name) and (config is None or isinstance(config, dict)):
            config = dict(config or {})
            config.setdefault(CACHE_CAPACITY_KEY, CPU_RUNTIME_CACHE_CAPACITY)
        if device_name is None and config is None:
            return original_compile_model(self, model, *args, **kwargs)
        if config is None:
            return original_compile_model(self, model, device_name, *args, **kwargs)
        return original_compile_model(self, model, device_name, config, *args, **kwargs)

    core_class.compile_model = capped_compile_model
    setattr(core_class, _PATCH_MARKER, True)


def install_ocr_memory_cap() -> None:
    try:
        import openvino
    except Exception as exc:  # OCR falls back elsewhere; never block startup
        logger.info(f"openvino not available, OCR cache cap skipped: {exc}")
        return
    patch_core_compile_model(openvino.Core)
