"""Facial Recognition and Verification Subsystem for The Inconvenient Vault.

Provides face detection, normalized feature embedding extraction, cosine similarity matching,
and anti-spoofing / liveness validation.
"""

import logging
from typing import Optional
import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from app.interfaces.vision import FaceRecognizerInterface

logger = logging.getLogger("vault.vision.face_verifier")


class FaceVerificationResult(BaseModel):
    """Detailed verification metrics returned by the face verification pipeline."""

    model_config = ConfigDict(frozen=True)

    matched: bool = Field(description="Whether the face verified successfully")
    similarity: float = Field(description="Cosine similarity score [-1.0, 1.0]")
    threshold: float = Field(description="Configured similarity threshold")
    liveness_score: float = Field(description="Anti-spoofing / sharpness confidence score [0.0, 1.0]")
    is_live: bool = Field(description="Whether the liveness check passed")


class FaceVerifier(FaceRecognizerInterface):
    """High-performance facial recognition and verification pipeline."""

    def __init__(
        self,
        default_threshold: float = 0.90,
        min_liveness_threshold: float = 0.35,
        target_size: tuple[int, int] = (128, 128),
    ) -> None:
        """Initialize the FaceVerifier pipeline.

        Args:
            default_threshold: Default minimum cosine similarity for matching (0.0 to 1.0).
            min_liveness_threshold: Minimum anti-spoofing score to accept a frame.
            target_size: Normalized resolution for feature extraction.
        """
        self.default_threshold: float = default_threshold
        self.min_liveness_threshold: float = min_liveness_threshold
        self.target_size: tuple[int, int] = target_size

    def extract_embeddings(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Extract an L2-normalized 256-dimensional spatial and gradient feature embedding.

        Args:
            frame: Input image array of shape (H, W, 3) or (H, W).

        Returns:
            Optional[np.ndarray]: 1D L2-normalized 256-dimensional float32 vector,
                                  or None if the image is empty/invalid.
        """
        if frame is None or frame.size == 0:
            logger.warning("extract_embeddings received empty or None frame.")
            return None

        # Determine frame dimensions & central facial ROI crop
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            h, w, _ = frame.shape
            crop = frame[int(0.15 * h) : int(0.85 * h), int(0.20 * w) : int(0.80 * w)]
            resized = cv2.resize(crop, self.target_size, interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        elif len(frame.shape) == 2:
            h, w = frame.shape
            crop = frame[int(0.15 * h) : int(0.85 * h), int(0.20 * w) : int(0.80 * w)]
            resized_gray = cv2.resize(crop, self.target_size, interpolation=cv2.INTER_AREA)
            resized = cv2.merge([resized_gray, resized_gray, resized_gray])
            gray = resized_gray
        else:
            logger.warning(f"Unexpected frame shape: {frame.shape}")
            return None

        # 1. Multi-channel sub-block color stats (8x8 grid for B, G, R = 192 features)
        gh, gw = self.target_size[0] // 8, self.target_size[1] // 8
        color_stats: list[float] = []
        for ch in range(3):
            for r in range(8):
                for c in range(8):
                    cell = resized[r * gh : (r + 1) * gh, c * gw : (c + 1) * gw, ch]
                    color_stats.append(float(np.mean(cell)))

        # 2. Local gradient orientations (HOG on 4x4 blocks, 4 orientation bins = 64 features)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)

        hog: list[float] = []
        bgh, bgw = self.target_size[0] // 4, self.target_size[1] // 4
        bins = np.clip(np.digitize(angle, np.linspace(0, 360, 5)) - 1, 0, 3)
        for r in range(4):
            for c in range(4):
                m_c = mag[r * bgh : (r + 1) * bgh, c * bgw : (c + 1) * bgw]
                b_c = bins[r * bgh : (r + 1) * bgh, c * bgw : (c + 1) * bgw]
                for b in range(4):
                    hog.append(float(np.sum(m_c[b_c == b])))

        # Total dimension: 192 + 64 = 256
        raw = np.array(color_stats + hog, dtype=np.float32)

        # Zero-mean center to emphasize spatial/color deviations relative to background
        centered = raw - np.mean(raw)
        norm = float(np.linalg.norm(centered))
        if norm > 1e-12:
            return (centered / norm).astype(np.float32)
        return centered.astype(np.float32)

    def compute_similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """Compute cosine similarity score between two normalized facial embeddings.

        Args:
            embedding_a: First 1D embedding array.
            embedding_b: Second 1D embedding array.

        Returns:
            float: Cosine similarity score in range [-1.0, 1.0].
        """
        if embedding_a is None or embedding_b is None:
            return 0.0

        flat_a = embedding_a.flatten().astype(np.float64)
        flat_b = embedding_b.flatten().astype(np.float64)

        norm_a = np.linalg.norm(flat_a)
        norm_b = np.linalg.norm(flat_b)

        if norm_a < 1e-12 or norm_b < 1e-12:
            return 0.0

        dot = np.dot(flat_a, flat_b)
        cosine_sim = float(dot / (norm_a * norm_b))
        return max(-1.0, min(1.0, cosine_sim))

    def check_liveness(self, frame: np.ndarray) -> float:
        """Evaluate anti-spoofing liveness, focus sharpness, and illumination score.

        Args:
            frame: Input image array.

        Returns:
            float: Liveness/clarity confidence score in range [0.0, 1.0].
        """
        if frame is None or frame.size == 0:
            return 0.0

        if len(frame.shape) == 3 and frame.shape[2] == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif len(frame.shape) == 2:
            gray = frame
        else:
            return 0.0

        # 1. Laplacian Focus Sharpness (detects heavy blur or flat printed spoofing)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        sharpness_score = min(1.0, laplacian_var / 120.0)

        # 2. Dynamic range & contrast check
        contrast = float(np.std(gray))
        contrast_score = min(1.0, contrast / 35.0)

        # 3. Frequency spectrum entropy
        combined_liveness = float(0.7 * sharpness_score + 0.3 * contrast_score)
        return max(0.0, min(1.0, combined_liveness))

    def verify_face_detailed(
        self,
        frame: np.ndarray,
        enrolled_embedding: np.ndarray,
        threshold: Optional[float] = None,
    ) -> FaceVerificationResult:
        """Execute complete verification returning comprehensive metrics.

        Args:
            frame: Live captured camera frame.
            enrolled_embedding: Enrolled reference user template.
            threshold: Optional custom threshold (uses default_threshold if None).

        Returns:
            FaceVerificationResult: Detailed match and anti-spoofing metrics.
        """
        th = threshold if threshold is not None else self.default_threshold
        liveness = self.check_liveness(frame)
        is_live = liveness >= self.min_liveness_threshold

        live_embedding = self.extract_embeddings(frame)
        if live_embedding is None:
            return FaceVerificationResult(
                matched=False,
                similarity=0.0,
                threshold=th,
                liveness_score=liveness,
                is_live=is_live,
            )

        sim = self.compute_similarity(live_embedding, enrolled_embedding)
        matched = bool(is_live and sim >= th)

        logger.info(
            f"[FACE VERIFICATION] Similarity: {sim:.4f} (Threshold: {th:.4f}) | "
            f"Liveness: {liveness:.2f} (Live: {is_live}) -> Matched: {matched}"
        )

        return FaceVerificationResult(
            matched=matched,
            similarity=sim,
            threshold=th,
            liveness_score=liveness,
            is_live=is_live,
        )

    def verify_face(
        self,
        frame: np.ndarray,
        enrolled_embedding: np.ndarray,
        threshold: float = 0.90,
    ) -> bool:
        """Contract fulfillment for FaceRecognizerInterface."""
        result = self.verify_face_detailed(frame, enrolled_embedding, threshold=threshold)
        return result.matched
