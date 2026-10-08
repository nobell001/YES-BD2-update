"""Windows Graphics Capture that stays SDR-correct while Windows HDR is on.

With HDR on, Windows composes SDR windows in linear scRGB, scaled by the
"SDR content brightness" (SDR white level, 1.0 = 80 nits).  Asked for 8-bit
BGRA (as ok-script does), WGC returns over-exposed frames on many systems -
the scaled light is clipped, every channel above ~160 turning 255 at a
240-nit white - and every absolute colour check drifts: template pixel
similarity, brightness percentiles, hue bands.  On Leo's PC (Windows 11 22H2,
NVIDIA, 240-nit white, 2026-09-30) the 8-bit frame of the game happened to be
right, which is not something to rely on for other players.

While HDR is on for the game's monitor, frames are captured as 16-bit float
scRGB and brought back to the SDR image the game rendered: divide by the
monitor's SDR white level, clip, encode sRGB.  Live with HDR on: the home
icons' colour distance was 0.0 and the ch15 route passed with the same badge
scores as without HDR.  With HDR off nothing changes (ok-script's 8-bit
path).  Leo 2026-09-30: HDR and the like must not break the judgement.
"""

from __future__ import annotations

import ctypes
import time

import cv2
import numpy as np

from ok.device.capture_methods.bitblt_utils import PBYTE
from ok.device.capture_methods.windows_graphics import WindowsGraphicsCaptureMethod
from ok.util.logger import Logger

logger = Logger.get_logger(__name__)

DXGI_FORMAT_R16G16B16A16_FLOAT = 10
FORMAT_8BIT = "8bit"
FORMAT_FLOAT = "fp16"
# How often the monitor's HDR state and SDR white level are re-read (a toggle
# mid-run is picked up within this time).
HDR_CHECK_SECONDS = 3.0
DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL = 11


def srgb_lut_for_float16(white: float) -> np.ndarray:
    """uint8 sRGB for every float16 bit pattern of linear scRGB light, with
    ``white`` (the SDR white level, 1.0 = 80 nits) mapped to 255."""

    values = np.arange(65536, dtype=np.uint32).astype(np.uint16).view(np.float16).astype(np.float64)
    values = np.nan_to_num(values, nan=0.0, posinf=white, neginf=0.0)
    linear = np.clip(values / max(float(white), 1e-3), 0.0, 1.0)
    encoded = np.where(
        linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055
    )
    return np.clip(np.round(encoded * 255.0), 0, 255).astype(np.uint8)


def float16_rgba_to_bgra(raw: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """(H, W, 4) uint16 float16 bit patterns, RGBA -> (H, W, 4) uint8 BGRA."""

    # 43 ms at 2K, 82 ms at 4K (reordering channels inside the lookup: 60/117).
    return cv2.cvtColor(lut[raw[:, :, :3]], cv2.COLOR_RGB2BGRA)


def display_hdr_white(hwnd: int) -> tuple[bool, float, str]:
    """(HDR on, SDR white level as a multiple of 80 nits, detail) for the
    monitor showing ``hwnd``; (False, 1.0, reason) when unknown.  Reuses
    ok-script's DisplayConfig helpers (its own HDR warning uses them)."""

    try:
        from ok.util import gpu_driver_settings as gds

        device_name = gds._monitor_device_name_from_hwnd(hwnd)
        for path in gds._query_active_display_paths():
            source_name = gds._displayconfig_source_name(path.sourceInfo)
            if device_name and source_name.lower() != device_name.lower():
                continue
            colour = gds._displayconfig_advanced_color_info(path.targetInfo)
            if colour is None or not colour.value & 0x2:
                return False, 1.0, f"{source_name or '?'}: HDR off"
            white = _sdr_white_level(gds, path.targetInfo)
            return True, white, f"{source_name or '?'}: HDR on, SDR white {white * 80:.0f} nits"
        return False, 1.0, f"no display path for {device_name or 'window'}"
    except Exception as exc:  # never let the check break capture
        return False, 1.0, f"HDR check failed: {exc}"


def _sdr_white_level(gds, target_info) -> float:
    class SdrWhiteLevel(ctypes.Structure):
        _fields_ = [
            ("header", gds.DISPLAYCONFIG_DEVICE_INFO_HEADER),
            ("SDRWhiteLevel", ctypes.c_uint32),
        ]

    info = SdrWhiteLevel()
    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_SDR_WHITE_LEVEL
    info.header.size = ctypes.sizeof(SdrWhiteLevel)
    info.header.adapterId = target_info.adapterId
    info.header.id = target_info.id
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.DisplayConfigGetDeviceInfo.argtypes = [ctypes.POINTER(gds.DISPLAYCONFIG_DEVICE_INFO_HEADER)]
    user32.DisplayConfigGetDeviceInfo.restype = ctypes.c_long
    status = user32.DisplayConfigGetDeviceInfo(
        ctypes.cast(ctypes.byref(info), ctypes.POINTER(gds.DISPLAYCONFIG_DEVICE_INFO_HEADER))
    )
    if status != 0 or not info.SDRWhiteLevel:
        return 1.0
    # "multiplier of 80 nits, multiplied by 1000" (1000 = 80 nits).
    return max(0.5, info.SDRWhiteLevel / 1000.0)


class HdrAwareWindowsGraphicsCapture(WindowsGraphicsCaptureMethod):
    def __init__(self, hwnd_window):
        # Set before the base __init__, which already starts the capture.
        self._pixel_format = FORMAT_8BIT
        self._hdr_white: float | None = None
        self._hdr_lut: np.ndarray | None = None
        self._hdr_checked_at = 0.0
        self._cputex_format = None
        super().__init__(hwnd_window)

    def start_or_stop(self, capture_cursor=False):
        had_pool = getattr(self, "frame_pool", None) is not None
        started = super().start_or_stop(capture_cursor)
        if started and self.frame_pool is not None:
            if not had_pool:
                # A fresh pool is 8-bit (base class): choose again.
                self._pixel_format = FORMAT_8BIT
            self._sync_hdr(force=not had_pool)
        return started

    def _sync_hdr(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._hdr_checked_at < HDR_CHECK_SECONDS:
            return
        self._hdr_checked_at = now
        enabled, white, detail = display_hdr_white(self.get_capture_hwnd())
        if enabled and (self._hdr_white is None or abs(white - self._hdr_white) > 1e-3):
            self._hdr_lut = srgb_lut_for_float16(white)
            logger.info(f"HDR capture: {detail}")
        self._hdr_white = white if enabled else None
        wanted = FORMAT_FLOAT if enabled else FORMAT_8BIT
        if wanted != self._pixel_format:
            logger.info(f"WGC pixel format {self._pixel_format} -> {wanted} ({detail})")
            self._pixel_format = wanted
            with self.lock:
                if self.frame_pool is not None and self.last_size is not None:
                    self.reset_framepool(self.last_size)

    def reset_framepool(self, size, reset_device=False):
        from ok.rotypes.Windows.Graphics.DirectX import DirectXPixelFormat

        logger.info(f"reset_framepool {self._pixel_format}")
        if self.cputex:
            self.cputex.Release()
            self.cputex = None
            self._cputex_format = None
        if reset_device:
            self.create_device()
        pixel_format = (
            DirectXPixelFormat.R16G16B16A16Float
            if self._pixel_format == FORMAT_FLOAT
            else DirectXPixelFormat.B8G8R8A8UIntNormalized
        )
        self.frame_pool.Recreate(self.rtdevice, pixel_format, 2, size)

    def convert_dx_frame(self, frame):
        """The base conversion, reading 16-bit float frames too."""

        dxdevice = self.dxdevice
        immediate_dc = self.immediatedc
        if not frame or dxdevice is None or immediate_dc is None:
            return None

        if frame.ContentSize.Width != self.last_size.Width or frame.ContentSize.Height != self.last_size.Height:
            logger.info("need_reset_framepool")
            self.last_size = frame.ContentSize
            self.reset_framepool(frame.ContentSize)
            return None

        need_reset_framepool = False
        need_reset_device = False
        tex = None
        mapped = False
        try:
            tex = frame.Surface.astype(self.IDirect3DDxgiInterfaceAccess).GetInterface(
                self.d3d11.ID3D11Texture2D.GUID).astype(self.d3d11.ID3D11Texture2D)
            desc = tex.GetDesc()
            if self.cputex is None or self._cputex_format != desc.Format:
                if self.cputex is not None:
                    self.cputex.Release()
                    self.cputex = None
                desc.Usage = self.d3d11.D3D11_USAGE_STAGING
                desc.CPUAccessFlags = self.d3d11.D3D11_CPU_ACCESS_READ
                desc.BindFlags = 0
                desc.MiscFlags = 0
                self.cputex = dxdevice.CreateTexture2D(ctypes.byref(desc), None)
                self._cputex_format = desc.Format

            immediate_dc.CopyResource(self.cputex, tex)
            mapinfo = immediate_dc.Map(self.cputex, 0, self.d3d11.D3D11_MAP_READ, 0)
            mapped = True
            height, width = self.last_size.Height, self.last_size.Width
            if self._cputex_format == DXGI_FORMAT_R16G16B16A16_FLOAT:
                raw = np.ctypeslib.as_array(
                    ctypes.cast(mapinfo.pData, ctypes.POINTER(ctypes.c_uint16)),
                    (height, mapinfo.RowPitch // 8, 4),
                )[:, :width]
                lut = self._hdr_lut if self._hdr_lut is not None else srgb_lut_for_float16(1.0)
                return float16_rgba_to_bgra(raw, lut)
            return np.ctypeslib.as_array(
                ctypes.cast(mapinfo.pData, PBYTE), (height, mapinfo.RowPitch // 4, 4)
            )[:, :width].copy()
        except OSError as e:
            if e.winerror == self.d3d11.DXGI_ERROR_DEVICE_REMOVED or e.winerror == self.d3d11.DXGI_ERROR_DEVICE_RESET:
                need_reset_framepool = True
                need_reset_device = True
                logger.error("convert_dx_frame win error", e)
            else:
                raise e
        finally:
            if mapped:
                immediate_dc.Unmap(self.cputex, 0)
            if tex is not None:
                tex.Release()

        if need_reset_framepool:
            self.reset_framepool(frame.ContentSize, need_reset_device)
        return None


def install() -> None:
    """Make ok-script build this capture wherever it would build WGC."""

    from ok.device.capture_methods import update

    if update.WindowsGraphicsCaptureMethod is not HdrAwareWindowsGraphicsCapture:
        update.WindowsGraphicsCaptureMethod = HdrAwareWindowsGraphicsCapture
