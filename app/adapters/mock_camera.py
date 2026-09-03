"""Mock Camera Adapter for The Inconvenient Vault.

Provides simulated camera frame capture without physical webcams or video hardware.
"""

import hashlib
from typing import Optional
import cv2
import numpy as np

from app.interfaces.vision import CameraCaptureInterface


class MockCameraAdapter(CameraCaptureInterface):
    """Synthetic camera adapter providing test frames, facial templates, and offline simulation."""

    def __init__(self, default_seed: int = 42, width: int = 640, height: int = 480) -> None:
        """Initialize the mock camera adapter.

        Args:
            default_seed: Random seed for generating reproducible synthetic face frames.
            width: Output frame width.
            height: Output frame height.
        """
        self._is_opened: bool = True
        self._width: int = width
        self._height: int = height
        self._current_frame: Optional[np.ndarray] = None
        self._default_seed: int = default_seed
        # Pre-generate default frame
        self._current_frame = self.generate_synthetic_face_frame(subject_seed=default_seed)

    def is_opened(self) -> bool:
        """Return whether the mock camera stream is active."""
        return self._is_opened

    def release(self) -> None:
        """Simulate releasing camera resources."""
        self._is_opened = False
        self._current_frame = None

    def set_offline(self, offline: bool = True) -> None:
        """Toggle virtual camera offline/online status."""
        self._is_opened = not offline

    def set_frame(self, frame: np.ndarray) -> None:
        """Inject a specific NumPy image frame to be returned by capture_frame()."""
        self._current_frame = frame.copy()

    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture the currently configured synthetic frame.

        Returns:
            Optional[np.ndarray]: Image array (H, W, 3), or None if offline/uninitialized.
        """
        if not self._is_opened:
            return None
        if self._current_frame is None:
            return self.generate_synthetic_face_frame(self._default_seed)
        return self._current_frame.copy()

    def generate_synthetic_face_frame(
        self,
        subject_seed: int = 42,
        noise_level: float = 0.02,
        blur: bool = False,
    ) -> np.ndarray:
        """Generate a deterministic synthetic face frame for computer vision testing.

        Creates an image containing structured facial geometry whose visual and
        spatial features vary distinctly with the subject_seed.

        Args:
            subject_seed: Identifier seed for the virtual subject.
            noise_level: Magnitude of Gaussian noise added for realistic variance.
            blur: If True, applies Gaussian blur to test anti-spoofing / blur detection.

        Returns:
            np.ndarray: BGR image frame (H, W, 3) with dtype uint8.
        """
        h_bytes = hashlib.sha256(f"subject_face_{subject_seed}".encode()).digest()
        v = [int(b) for b in h_bytes]
        rng = np.random.RandomState(v[0] * 256 + v[1])

        h, w = self._height, self._width
        frame = np.full((h, w, 3), int(30 + (v[2] % 40)), dtype=np.uint8)

        cx = w // 2 + int((v[3] % 31) - 15)
        cy = h // 2 + int((v[4] % 31) - 15)

        skin_tones = [
            (130, 160, 210),  # Fair
            (110, 140, 190),  # Tan
            (80, 110, 160),   # Olive
            (50, 70, 110),    # Dark
            (140, 180, 230),  # Pale
            (100, 130, 170),  # Medium
        ]
        skin_color = skin_tones[v[5] % len(skin_tones)]

        head_w = int(70 + (v[6] % 50))
        head_h = int(100 + (v[7] % 60))
        cv2.ellipse(frame, (cx, cy), (head_w, head_h), 0, 0, 360, skin_color, -1)

        hair_colors = [
            (20, 20, 20),
            (30, 50, 80),
            (40, 80, 130),
            (160, 160, 160),
            (30, 30, 60),
            (90, 40, 20),
        ]
        hair_c = hair_colors[v[8] % len(hair_colors)]
        hair_style = v[9] % 4
        if hair_style == 0:
            cv2.ellipse(
                frame,
                (cx, cy - int(head_h * 0.6)),
                (int(head_w * 1.1), int(head_h * 0.5)),
                0,
                180,
                360,
                hair_c,
                -1,
            )
        elif hair_style == 1:
            cv2.rectangle(
                frame,
                (cx - int(head_w * 1.1), cy - head_h),
                (cx + int(head_w * 1.1), cy - int(head_h * 0.3)),
                hair_c,
                -1,
            )
        elif hair_style == 2:
            cv2.circle(frame, (cx, cy - int(head_h * 0.7)), int(head_w * 0.9), hair_c, -1)

        eye_dx = int(20 + (v[10] % 30))
        eye_dy = int(12 + (v[11] % 25))
        eye_r = int(5 + (v[12] % 8))
        iris_c = (int(v[13] % 220), int(v[14] % 220), int(v[15] % 220))
        cv2.circle(frame, (cx - eye_dx, cy - eye_dy), eye_r + 4, (245, 245, 245), -1)
        cv2.circle(frame, (cx - eye_dx, cy - eye_dy), eye_r, iris_c, -1)
        cv2.circle(frame, (cx + eye_dx, cy - eye_dy), eye_r + 4, (245, 245, 245), -1)
        cv2.circle(frame, (cx + eye_dx, cy - eye_dy), eye_r, iris_c, -1)

        if (v[16] % 2) == 1:
            cv2.rectangle(
                frame,
                (cx - eye_dx - 14, cy - eye_dy - 12),
                (cx - eye_dx + 14, cy - eye_dy + 12),
                (20, 20, 20),
                2,
            )
            cv2.rectangle(
                frame,
                (cx + eye_dx - 14, cy - eye_dy - 12),
                (cx + eye_dx + 14, cy - eye_dy + 12),
                (20, 20, 20),
                2,
            )
            cv2.line(
                frame,
                (cx - eye_dx + 14, cy - eye_dy),
                (cx + eye_dx - 14, cy - eye_dy),
                (20, 20, 20),
                2,
            )

        nose_len = int(15 + (v[17] % 25))
        cv2.line(
            frame,
            (cx, cy - 4),
            (cx, cy + nose_len),
            (max(0, skin_color[0] - 25), max(0, skin_color[1] - 25), max(0, skin_color[2] - 25)),
            2,
        )

        mouth_w = int(15 + (v[18] % 35))
        mouth_y = cy + nose_len + int(10 + (v[19] % 20))
        cv2.ellipse(frame, (cx, mouth_y), (mouth_w, 6), 0, 0, 180, (50, 50, 160), -1)

        if (v[20] % 2) == 1:
            cv2.ellipse(
                frame,
                (cx, mouth_y + 15),
                (int(head_w * 0.7), int(head_h * 0.35)),
                0,
                0,
                180,
                hair_c,
                -1,
            )

        if noise_level > 0:
            noise = (rng.randn(h, w, 3) * (noise_level * 255)).astype(np.int16)
            noisy_frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            frame = noisy_frame

        if blur:
            frame = cv2.GaussianBlur(frame, (31, 31), 0)

        self._current_frame = frame
        return frame
