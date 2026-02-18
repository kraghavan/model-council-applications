"""Code analysis module for deep PR review."""

from council.analysis.code_context import CodeContextAnalyzer
from council.analysis.similarity import SimilaritySearch
from council.analysis.embeddings import get_embedding, EmbeddingProvider
from council.analysis.fingerprint import (
    IssueFingerprint,
    create_issue_fingerprint,
    categorize_issue,
    extract_function_name,
    format_previous_issues,
)

__all__ = [
    "CodeContextAnalyzer",
    "SimilaritySearch", 
    "get_embedding",
    "EmbeddingProvider",
    "IssueFingerprint",
    "create_issue_fingerprint",
    "categorize_issue",
    "extract_function_name",
    "format_previous_issues",
]
