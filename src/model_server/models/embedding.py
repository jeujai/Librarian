"""Embedding model wrapper for sentence-transformers."""

import logging
import time
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Global model instance
_embedding_model: Optional["EmbeddingModel"] = None


class EmbeddingModel:
    """Wrapper for sentence-transformers embedding model."""
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
        cache_dir: Optional[str] = None
    ):
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self._loaded = False
        self._load_time_seconds: Optional[float] = None
        self._dimensions: Optional[int] = None
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
    def dimensions(self) -> Optional[int]:
        """Get embedding dimensions."""
        return self._dimensions
    
    @property
    def error(self) -> Optional[str]:
        """Get error message if loading failed."""
        return self._error
    
    def load(self) -> bool:
        """Load the embedding model."""
        if self._loaded:
            return True
        
        logger.info(f"Loading embedding model: {self.model_name}")
        start_time = time.time()
        
        try:
            from sentence_transformers import SentenceTransformer
            
            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=self.cache_dir
            )
            
            # Get embedding dimensions by encoding a test sentence
            test_embedding = self._model.encode(["test"], convert_to_numpy=True)
            self._dimensions = test_embedding.shape[1]
            
            self._load_time_seconds = time.time() - start_time
            self._loaded = True
            self._error = None
            
            logger.info(
                f"Embedding model loaded successfully: {self.model_name} "
                f"(dimensions={self._dimensions}, time={self._load_time_seconds:.2f}s)"
            )
            return True
            
        except Exception as e:
            self._error = str(e)
            self._load_time_seconds = time.time() - start_time
            logger.error(f"Failed to load embedding model: {e}")
            return False
    
    def encode(
        self,
        texts: List[str],
        batch_size: int = 32,
        normalize: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of texts to encode
            batch_size: Batch size for encoding
            normalize: Whether to normalize embeddings
            
        Returns:
            List of embedding vectors
        """
        if not self._loaded:
            raise RuntimeError("Embedding model not loaded")
        
        if not texts:
            return []
        
        try:
            embeddings = self._model.encode(
                texts,
                batch_size=batch_size,
                convert_to_numpy=True,
                normalize_embeddings=normalize,
                show_progress_bar=False
            )
            
            # Convert to list of lists for JSON serialization
            return embeddings.tolist()
            
        except Exception as e:
            logger.error(f"Error encoding texts: {e}")
            raise
    
    def get_status(self) -> dict:
        """Get model status information."""
        return {
            "name": self.model_name,
            "status": "loaded" if self._loaded else "not_loaded",
            "device": self.device,
            "dimensions": self._dimensions,
            "load_time_seconds": self._load_time_seconds,
            "error": self._error
        }


def get_embedding_model() -> Optional[EmbeddingModel]:
    """Get the global embedding model instance."""
    return _embedding_model


def initialize_embedding_model(
    model_name: str = "all-MiniLM-L6-v2",
    device: str = "cpu",
    cache_dir: Optional[str] = None
) -> EmbeddingModel:
    """Initialize the global embedding model."""
    global _embedding_model
    
    _embedding_model = EmbeddingModel(
        model_name=model_name,
        device=device,
        cache_dir=cache_dir
    )
    _embedding_model.load()
    
    return _embedding_model
