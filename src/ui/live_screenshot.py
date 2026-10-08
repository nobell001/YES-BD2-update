import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel

from src.ui.traditional import ui_text

PREVIEW_INTERVAL_MS = 50
PREVIEW_MIN_WIDTH = 240
PREVIEW_ASPECT_WIDTH = 16
PREVIEW_ASPECT_HEIGHT = 9
CAPTURE_TIMEOUT_SECONDS = 2.0


class LivePreviewLabel(QLabel):
    def __init__(self):
        super().__init__()
        self._image: QImage | None = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(PREVIEW_MIN_WIDTH, self.heightForWidth(PREVIEW_MIN_WIDTH))
        size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        size_policy.setHeightForWidth(True)
        self.setSizePolicy(size_policy)
        self.setText(ui_text("等待截图"))
        self.setStyleSheet(
            "QLabel {background-color: #111111;border-radius: 6px;color: rgba(255, 255, 255, 150);}"
        )

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return max(1, round(width * PREVIEW_ASPECT_HEIGHT / PREVIEW_ASPECT_WIDTH))

    def sizeHint(self):
        return QSize(480, 270)

    def set_image(self, image: QImage | None):
        self._image = image
        self._update_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_aspect_height()
        self._update_pixmap()

    def _sync_aspect_height(self):
        width = self.width()
        if width <= 0:
            return

        target_height = self.heightForWidth(width)
        if self.minimumHeight() == target_height and self.maximumHeight() == target_height:
            return

        self.setMinimumHeight(target_height)
        self.setMaximumHeight(target_height)

    def _update_pixmap(self):
        if self._image is None or self._image.isNull():
            self.clear()
            self.setText(ui_text("等待截图"))
            return

        pixmap = QPixmap.fromImage(self._image)
        scaled = pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(scaled)


class LiveScreenshotWidget(QWidget):
    frame_ready = Signal(QImage, str)
    status_ready = Signal(str)

    def __init__(self):
        super().__init__()
        self._capture_executor = self._new_capture_executor()
        self._capture_pending = False
        self._capture_pending_at = 0.0
        self._capture_future = None
        self._last_status = ""
        self._last_frame_at = 0.0
        self._active = False
        # A frame the running task captured this recently is shown as is.
        self.reuse_frame_age = 0.08
        # When the task has no fresh frame (it is waiting), capture our own at
        # most this often; 0 = on every tick.
        self.own_capture_gap = 0.0
        self._own_capture_at = 0.0

        self.preview = LivePreviewLabel()
        self.status_label = CaptionLabel(ui_text("等待选择窗口"))
        self.status_label.setStyleSheet("color: #bbbbbb;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.status_label)

        self.frame_ready.connect(self._display_frame)
        self.status_ready.connect(self._display_empty)

        self.timer = QTimer(self)
        self.timer.setInterval(PREVIEW_INTERVAL_MS)
        self.timer.timeout.connect(self._request_frame)

        self.destroyed.connect(self._shutdown)

    def showEvent(self, event):
        super().showEvent(event)
        self.start_preview()

    def hideEvent(self, event):
        self.stop_preview()
        super().hideEvent(event)

    def start_preview(self):
        self._active = True
        if not self.timer.isActive():
            self.timer.start()
        self._request_frame()

    def stop_preview(self):
        self._active = False
        if self.timer.isActive():
            self.timer.stop()

    def _request_frame(self):
        if not self._active or not self.isVisible():
            return
        if self._capture_pending:
            if time.time() - self._capture_pending_at <= CAPTURE_TIMEOUT_SECONDS:
                return
            self.status_ready.emit("截图超时，正在重试")
            self._restart_capture_executor()

        try:
            from ok import og

            if getattr(og, "exit_event", None) is not None and og.exit_event.is_set():
                self.timer.stop()
                return
        except Exception:
            pass

        self._capture_pending = True
        self._capture_pending_at = time.time()
        # Shrink to the preview's size off the UI thread: scaling a 4K frame
        # on the UI thread several times a second costs window smoothness.
        size = self.preview.size()
        future = self._capture_executor.submit(self._capture_image, (size.width(), size.height()))
        self._capture_future = future
        future.add_done_callback(self._capture_finished)

    def _capture_finished(self, future):
        if future is not self._capture_future:
            return
        try:
            image, status = future.result()
            if not self._active or (image is None and status is None):
                # None/None: no new picture this tick, keep the one shown.
                return
            if image is not None:
                self.frame_ready.emit(image, status)
            else:
                self.status_ready.emit(status)
        except Exception as exc:
            self.status_ready.emit(ui_text("截图失败：{error}").format(error=exc))
        finally:
            if future is self._capture_future:
                self._capture_pending = False
                self._capture_pending_at = 0.0
                self._capture_future = None

    def _capture_image(
        self, fit: tuple[int, int] | None = None
    ) -> tuple[QImage | None, str | None]:
        from ok import og

        device_manager = getattr(og, "device_manager", None)
        if device_manager is None:
            return None, "设备管理未就绪"

        preferred = device_manager.get_preferred_device()
        if preferred is None:
            return None, "等待选择窗口"

        method = getattr(device_manager, "capture_method", None)
        if method is None:
            return None, "等待选择截图方式"

        try:
            if hasattr(method, "connected") and not method.connected():
                return None, "截图方式未连接"
        except Exception:
            return None, "截图方式未连接"

        frame = self._recent_executor_frame(self.reuse_frame_age)
        if frame is None:
            if time.time() - self._own_capture_at < self.own_capture_gap:
                return None, None
            self._own_capture_at = time.time()
            frame = method.get_frame()

        if frame is None:
            return None, "暂无截图"

        height, width = frame.shape[:2]
        image = self._frame_to_image(self._fit(frame, fit))
        method_name = method.get_name() if hasattr(method, "get_name") else str(method)
        return image, f"{width}x{height} · {method_name}"

    @staticmethod
    def _fit(frame, fit: tuple[int, int] | None):
        """``frame`` shrunk to fit ``fit`` (width, height); never enlarged."""
        if not fit or fit[0] <= 0 or fit[1] <= 0:
            return frame
        height, width = frame.shape[:2]
        scale = min(fit[0] / width, fit[1] / height)
        if scale >= 1.0:
            return frame
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)

    @staticmethod
    def _recent_executor_frame(max_age: float = 0.08):
        from ok import og

        executor = getattr(og, "executor", None)
        if executor is None:
            return None

        frame = executor.nullable_frame()
        if frame is None:
            return None

        last_frame_time = getattr(executor, "_last_frame_time", 0)
        if time.time() - last_frame_time > max_age:
            return None

        return frame

    @staticmethod
    def _frame_to_image(frame) -> QImage:
        if len(frame.shape) == 2:
            rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        elif frame.shape[2] == 4:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        height, width = rgb.shape[:2]
        bytes_per_line = rgb.strides[0]
        return QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888,
        ).copy()

    def latest_frame(self, max_age_seconds: float = 2.0):
        """Return a BGR copy of the latest frame already delivered to the UI."""
        image = self.preview._image
        if image is None or image.isNull() or self._last_frame_at <= 0:
            return None, None

        age = max(0.0, time.time() - self._last_frame_at)
        if age > max(0.0, max_age_seconds):
            return None, age

        converted = image.convertToFormat(QImage.Format_RGB888)
        height = converted.height()
        width = converted.width()
        bytes_per_line = converted.bytesPerLine()
        rgb_rows = np.frombuffer(
            converted.bits(),
            dtype=np.uint8,
            count=height * bytes_per_line,
        ).reshape(height, bytes_per_line)
        rgb = rgb_rows[:, : width * 3].reshape(height, width, 3)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), age

    def _display_frame(self, image: QImage, status: str):
        if not self._active:
            return
        self._last_frame_at = time.time()
        self.preview.set_image(image)
        self._display_status(status)

    def _display_status(self, status: str):
        if not self._active:
            return
        if status == self._last_status:
            return
        self._last_status = status
        self.status_label.setText(ui_text(status))

    def _display_empty(self, status: str):
        if not self._active:
            return
        self.preview.set_image(None)
        self._display_status(status)

    def _shutdown(self):
        self.stop_preview()
        self._capture_executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _new_capture_executor():
        return ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="LiveScreenshot",
        )

    def _restart_capture_executor(self):
        old_executor = self._capture_executor
        self._capture_executor = self._new_capture_executor()
        self._capture_pending = False
        self._capture_pending_at = 0.0
        self._capture_future = None
        old_executor.shutdown(wait=False, cancel_futures=True)

