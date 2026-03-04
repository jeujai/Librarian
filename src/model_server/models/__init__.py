"""Model wrappers for embedding and NLP models."""

from .embedding import EmbeddingModel, get_embedding_model
from .nlp import NLPModel, get_nlp_model

__all__ = ["EmbeddingModel", "get_embedding_model", "NLPModel", "get_nlp_model"]
