"""Model reviewers package."""

from council.models.base import BaseReviewer, ReviewResult, ReviewIssue
from council.models.claude import ClaudeReviewer
from council.models.gemini import GeminiReviewer
from council.models.ollama import OllamaReviewer


def get_reviewer(model_name: str) -> BaseReviewer:
    """Factory function to get a reviewer by name."""
    reviewers = {
        "claude": ClaudeReviewer,
        "gemini": GeminiReviewer,
        "ollama": OllamaReviewer,
    }
    
    if model_name not in reviewers:
        raise ValueError(f"Unknown model: {model_name}. Available: {list(reviewers.keys())}")
    
    return reviewers[model_name]()


__all__ = [
    "BaseReviewer",
    "ReviewResult", 
    "ReviewIssue",
    "ClaudeReviewer",
    "GeminiReviewer",
    "OllamaReviewer",
    "get_reviewer",
]
