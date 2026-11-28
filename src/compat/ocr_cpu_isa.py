"""Keep the OCR's CPU kernels off Intel AMX.

OpenVINO runs the OCR in bfloat16 on any CPU that can, and on Intel Xeon
CPUs with AMX (Sapphire/Emerald/Granite Rapids) its oneDNN kernels then use
the AMX tile unit.  On some Windows machines with such a CPU that dies with
0xC000001D (illegal instruction) at the first OCR call, before any Python
error can be shown.

Proven 2026-11-28 on GitHub's Windows Server 2025 runners (YES-BD2 Build,
v0.4.2/v0.4.17/v0.4.20): only the Xeon Platinum 8573C machines that expose
AMX crash, every time; first kernel made was ``convolution,jit:
avx10_1_512_amx``.  Same machine, same tests: ONEDNN_MAX_CPU_ISA=
AVX512_CORE_FP16 (bfloat16 without AMX) passes, as do AVX512_CORE_BF16,
AVX512_CORE_VNNI and a float32 precision hint; AVX512_CORE_AMX crashes.
The 8573C machines without AMX and a Xeon 6973P-C with AMX pass either way.

Gaming PCs (Intel Core, AMD Ryzen) have no AMX, so this cap changes nothing
for them; a Xeon with AMX keeps bfloat16 through AVX-512 instead.  A value
the user set themselves is kept.  oneDNN reads the cap once, at its first
CPU check, so this must run before any OCR model is built: src/__init__.py.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

ISA_ENV = "ONEDNN_MAX_CPU_ISA"
NO_AMX_ISA = "AVX512_CORE_FP16"


def install_no_amx_cap(environ: MutableMapping[str, str] | None = None) -> bool:
    """Cap oneDNN below AMX unless a cap is already set.  True if set here."""

    environ = os.environ if environ is None else environ
    if environ.get(ISA_ENV, "").strip():
        return False
    environ[ISA_ENV] = NO_AMX_ISA
    return True
