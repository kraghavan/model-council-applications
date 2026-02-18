"""Code analysis module for deep PR review."""

from council.analysis.code_context import CodeContextAnalyzer
from council.analysis.similarity import SimilaritySearch
from council.analysis.embeddings import get_embedding, EmbeddingProvider

__all__ = [
    "CodeContextAnalyzer",
    "SimilaritySearch", 
    "get_embedding",
    "EmbeddingProvider",
]
