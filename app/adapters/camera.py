"""Production Camera Adapter for The Inconvenient Vault.

Captures real live video frames from physical webcams (USB, built-in, or CSI cameras)
using OpenCV (cv2.VideoCapture) with thread safety, auto-exposure warming, and graceful recovery.
"""

import logging
import os
import threading
from typing import Optional
import cv2
import numpy as np

from app.interfaces.vision import CameraCaptureInterface

logger = logging.getLogger("vault.adapters.camera")


class OpenCVCameraAdapter(CameraCaptureInterface):
    """Production video capture adapter interfacing directly with physical hardware cameras."""

    def __init__(
        self,
        camera_index: Optional[int] = None,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        auto_open: bool = True,
    ) -> None:
        """Initialize the OpenCV Camera Adapter.

        Args:
            camera_index: Device index (e.g. 0 for default webcam, 1 for external USB camera).
                          If None, reads VAULT_CAMERA_INDEX from environment (default: 0).
            width: Target frame width resolution (default: 640).
            height: Target frame height resolution (default: 480).
            fps: Target capture frame rate (default: 30).
            auto_open: If True, immediately opens the physical camera device.
        """
        if camera_index is None:
            env_index = os.environ.get("VAULT_CAMERA_INDEX", "0")
            try:
                self._camera_index = int(env_index)
            except ValueError:
                self._camera_index = 0
        else:
            self._camera_index = camera_index

        self._width = width
        self._height = height
        self._fps = fps
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._is_opened = False

        if auto_open:
            self.open()

    def open(self) -> bool:
        """Open the physical video capture device and configure resolution.

        Returns:
            bool: True if the camera opened successfully, False otherwise.
        """
        with self._lock:
            if self._cap is not None and self._cap.isOpened():
                self._is_opened = True
                return True

            logger.info(f"Opening physical camera device index {self._camera_index}...")
            try:
                # Use CAP_DSHOW on Windows for fast device initialization if supported
                if os.name == "nt":
                    self._cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
                    if not self._cap.isOpened():
                        self._cap = cv2.VideoCapture(self._camera_index)
                else:
                    self._cap = cv2.VideoCapture(self._camera_index)

                if self._cap.isOpened():
                    self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
                    self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
                    self._cap.set(cv2.CAP_PROP_FPS, self._fps)
                    self._is_opened = True
                    logger.info(
                        f"Physical camera device {self._camera_index} ready "
                        f"({self._width}x{self._height} @ {self._fps}fps)."
                    )
                    return True
                else:
                    logger.warning(f"Failed to open physical camera device {self._camera_index}.")
                    self._is_opened = False
                    return False
            except Exception as ex:
                logger.error(f"Error opening camera device {self._camera_index}: {ex}")
                self._is_opened = False
                return False

    def is_opened(self) -> bool:
        """Return whether the physical video capture stream is active."""
        with self._lock:
            return self._is_opened and self._cap is not None and self._cap.isOpened()

    def release(self) -> None:
        """Release underlying physical camera hardware resources."""
        with self._lock:
            self._is_opened = False
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception as ex:
                    logger.warning(f"Error releasing camera: {ex}")
                self._cap = None
            logger.info(f"Physical camera device {self._camera_index} released.")

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single image frame from the live video stream.

        Returns:
            Optional[np.ndarray]: BGR image array of shape (H, W, 3), or None if capture failed.
        """
        with self._lock:
            if not self._is_opened or self._cap is None or not self._cap.isOpened():
                # Attempt lazy reconnect
                if not self.open():
                    return None

            try:
                ret, frame = self._cap.read()
                if not ret or frame is None or frame.size == 0:
                    logger.warning("Camera read returned empty frame. Attempting re-initialization...")
                    self._cap.release()
                    self._cap = cv2.VideoCapture(self._camera_index)
                    ret, frame = self._cap.read()
                    if not ret or frame is None:
                        logger.error("Failed to capture frame from physical camera.")
                        return None

                return frame
            except Exception as ex:
                logger.error(f"Exception during camera frame capture: {ex}")
                return None

    def capture_warm_frame(self, discard_count: int = 5) -> Optional[np.ndarray]:
        """Capture a frame after discarding initial frames to allow auto-exposure to stabilize.

        Args:
            discard_count: Number of initial buffer frames to discard (default: 5).

        Returns:
            Optional[np.ndarray]: Stabilized BGR image frame, or None if capture failed.
        """
        frame: Optional[np.ndarray] = None
        for _ in range(max(1, discard_count)):
            frame = self.capture_frame()
        return frame
