"""Cross-encoder model wrapper for reranking."""

import logging
import time
from typing import List, Optional

import numpy as np
from scipy.special import expit

logger = logging.getLogger(__name__)

# Global model instance
_cross_encoder_model: Optional["CrossEncoderModel"] = None


class CrossEncoderModel:
    """Wrapper for sentence-transformers CrossEncoder model."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
        cache_dir: Optional[str] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self._loaded = False
        self._load_time_seconds: Optional[float] = None
        self._error: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._loaded

    @property
    def load_time_seconds(self) -> Optional[float]:
        """Get model load time in seconds."""
        return self._load_time_seconds

    @property
    def error(self) -> Optional[str]:
        """Get error message if loading failed."""
        return self._error

    def load(self) -> bool:
        """Load the cross-encoder model."""
        if self._loaded:
            return True

        logger.info(f"Loading cross-encoder model: {self.model_name}")
        start_time = time.time()

        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                device=self.device,
            )

            self._load_time_seconds = time.time() - start_time
            self._loaded = True
            self._error = None

            logger.info(
                f"Cross-encoder model loaded successfully: {self.model_name} "
                f"(time={self._load_time_seconds:.2f}s)"
            )
            return True

        except Exception as e:
            self._error = str(e)
            self._load_time_seconds = time.time() - start_time
            logger.error(f"Failed to load cross-encoder model: {e}")
            return False

    def predict(self, query: str, documents: List[str]) -> List[float]:
        """
        Score query-document pairs using the cross-encoder.

        Args:
            query: Query text.
            documents: List of document texts to score against the query.

        Returns:
            List of sigmoid-normalized scores in [0, 1], one per document.
        """
        if not self._loaded:
            raise RuntimeError("Cross-encoder model not loaded")

        if not documents:
            return []

        pairs = [(query, doc) for doc in documents]
        raw_scores = self._model.predict(pairs)
        scores = expit(np.asarray(raw_scores))
        return scores.tolist()

    def get_status(self) -> dict:
        """Get model status information."""
        return {
            "name": self.model_name,
            "status": "loaded" if self._loaded else "not_loaded",
            "device": self.device,
            "load_time_seconds": self._load_time_seconds,
            "error": self._error,
        }


def get_cross_encoder_model() -> Optional[CrossEncoderModel]:
    """Get the global cross-encoder model instance."""
    return _cross_encoder_model


def initialize_cross_encoder_model(
    model_name: str = "BAAI/bge-reranker-v2-m3",
    device: str = "cpu",
    cache_dir: Optional[str] = None,
) -> CrossEncoderModel:
    """Initialize the global cross-encoder model."""
    global _cross_encoder_model

    _cross_encoder_model = CrossEncoderModel(
        model_name=model_name,
        device=device,
        cache_dir=cache_dir,
    )
    _cross_encoder_model.load()

    return _cross_encoder_model
