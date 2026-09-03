"""Computer Vision and Facial Recognition Interface Contracts.

Decouples the authentication engine from physical camera devices (USB webcams,
CSI cameras, ESP32-CAM HTTP streams) and deep learning biometric backends.
"""

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np


class CameraCaptureInterface(ABC):
    """Abstract Base Class for video capture devices and frame providers."""

    @abstractmethod
    def capture_frame(self) -> Optional[np.ndarray]:
        """Capture a single image frame as a NumPy array (BGR/RGB format).

        Returns:
            Optional[np.ndarray]: Image array of shape (H, W, 3), or None if capture failed.
        """
        pass

    @abstractmethod
    def release(self) -> None:
        """Release underlying video capture resources or network stream sockets."""
        pass

    @abstractmethod
    def is_opened(self) -> bool:
        """Check if the video capture device is ready and streaming.

        Returns:
            bool: True if ready, False otherwise.
        """
        pass


class FaceRecognizerInterface(ABC):
    """Abstract Base Class for biometric facial detection, feature extraction, and verification."""

    @abstractmethod
    def extract_embeddings(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Detect face in frame and extract a normalized 1D feature embedding vector.

        Args:
            frame: Input image array of shape (H, W, 3) or (H, W).

        Returns:
            Optional[np.ndarray]: L2-normalized 1D floating-point embedding vector,
                                  or None if no face detected or frame invalid.
        """
        pass

    @abstractmethod
    def compute_similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """Compute cosine similarity score between two normalized facial embeddings.

        Args:
            embedding_a: First 1D embedding array.
            embedding_b: Second 1D embedding array.

        Returns:
            float: Cosine similarity score in range [-1.0, 1.0].
        """
        pass

    @abstractmethod
    def check_liveness(self, frame: np.ndarray) -> float:
        """Evaluate anti-spoofing / liveness / clarity score from the frame.

        Args:
            frame: Input image array.

        Returns:
            float: Liveness/clarity confidence score in range [0.0, 1.0].
        """
        pass

    @abstractmethod
    def verify_face(
        self,
        frame: np.ndarray,
        enrolled_embedding: np.ndarray,
        threshold: float = 0.85,
    ) -> bool:
        """Perform end-to-end facial verification against an enrolled user template.

        Args:
            frame: Input live image frame.
            enrolled_embedding: Pre-enrolled reference facial embedding.
            threshold: Minimum cosine similarity required to authenticate.

        Returns:
            bool: True if face matches enrolled template above threshold and passes liveness;
                  False otherwise.
        """
        pass
