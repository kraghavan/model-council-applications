"""Base class for model reviewers."""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ReviewIssue:
    """A single issue found in a PR."""

    severity: str  # critical, major, minor, nit
    file: str | None
    line: int | None
    description: str


@dataclass
class ReviewResult:
    """Result from a single model's review."""

    model_name: str
    score: float
    verdict: str  # APPROVE, REQUEST_CHANGES, COMMENT
    summary: str
    issues: list[ReviewIssue] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def from_error(cls, model_name: str, error: str) -> "ReviewResult":
        """Create an error result."""
        return cls(
            model_name=model_name,
            score=0.0,
            verdict="ERROR",
            summary=f"Review failed: {error}",
            error=error,
        )


def parse_review_json(model_name: str, response: str) -> ReviewResult:
    """Parse a model's JSON response into a ReviewResult."""
    # Try to extract JSON from the response (models sometimes add markdown)
    json_match = re.search(r"\{[\s\S]*\}", response)
    if not json_match:
        return ReviewResult.from_error(model_name, "No JSON found in response")
    
    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        return ReviewResult.from_error(model_name, f"Invalid JSON: {e}")
    
    # Parse issues
    issues = []
    for issue_data in data.get("issues", []):
        issues.append(ReviewIssue(
            severity=issue_data.get("severity", "minor"),
            file=issue_data.get("file"),
            line=issue_data.get("line"),
            description=issue_data.get("description", ""),
        ))
    
    return ReviewResult(
        model_name=model_name,
        score=float(data.get("score", 0.5)),
        verdict=data.get("verdict", "COMMENT"),
        summary=data.get("summary", ""),
        issues=issues,
        positives=data.get("positives", []),
    )


class BaseReviewer(ABC):
    """Abstract base class for model reviewers."""

    name: str = "base"

    @abstractmethod
    async def review(self, pr_info: dict, diff: str) -> ReviewResult:
        """Review a PR and return the result."""
        pass
