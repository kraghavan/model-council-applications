"""Aggregate results from multiple reviewers into a council verdict."""

from dataclasses import dataclass, field
from collections import Counter

from council.models.base import ReviewResult, ReviewIssue


@dataclass
class CouncilVerdict:
    """Aggregated verdict from the council."""

    score: float
    verdict: str  # APPROVE, REQUEST_CHANGES, COMMENT
    consensus: str  # full, partial, split
    summary: str
    individual_reviews: list[ReviewResult]
    key_issues: list[dict] = field(default_factory=list)
    
    @property
    def emoji(self) -> str:
        """Get verdict emoji."""
        return {
            "APPROVE": "✅",
            "REQUEST_CHANGES": "🔴",
            "COMMENT": "💬",
            "ERROR": "❌",
        }.get(self.verdict, "❓")


def aggregate_reviews(reviews: list[ReviewResult], threshold: float = 0.7) -> CouncilVerdict:
    """Aggregate multiple reviews into a council verdict."""
    # Filter out errors
    valid_reviews = [r for r in reviews if r.error is None]
    error_reviews = [r for r in reviews if r.error is not None]
    
    if not valid_reviews:
        return CouncilVerdict(
            score=0.0,
            verdict="ERROR",
            consensus="none",
            summary="All reviewers encountered errors.",
            individual_reviews=reviews,
        )
    
    # Calculate average score
    avg_score = sum(r.score for r in valid_reviews) / len(valid_reviews)
    
    # Determine verdict based on threshold and individual verdicts
    verdicts = Counter(r.verdict for r in valid_reviews)
    
    if verdicts.get("REQUEST_CHANGES", 0) > 0:
        # Any REQUEST_CHANGES means the council requests changes
        final_verdict = "REQUEST_CHANGES"
    elif avg_score >= threshold:
        final_verdict = "APPROVE"
    else:
        final_verdict = "COMMENT"
    
    # Determine consensus level
    if len(set(r.verdict for r in valid_reviews)) == 1:
        consensus = "full"
    elif verdicts.most_common(1)[0][1] > len(valid_reviews) / 2:
        consensus = "partial"
    else:
        consensus = "split"
    
    # Collect and deduplicate issues
    issue_map: dict[str, dict] = {}
    for review in valid_reviews:
        for issue in review.issues:
            key = f"{issue.file}:{issue.line}:{issue.description[:50]}"
            if key not in issue_map:
                issue_map[key] = {
                    "severity": issue.severity,
                    "file": issue.file,
                    "line": issue.line,
                    "description": issue.description,
                    "raised_by": [review.model_name],
                }
            else:
                issue_map[key]["raised_by"].append(review.model_name)
                # Escalate severity if multiple models flag it
                if issue.severity == "critical":
                    issue_map[key]["severity"] = "critical"
                elif issue.severity == "major" and issue_map[key]["severity"] != "critical":
                    issue_map[key]["severity"] = "major"
    
    # Sort issues by severity
    severity_order = {"critical": 0, "major": 1, "minor": 2, "nit": 3}
    key_issues = sorted(
        issue_map.values(),
        key=lambda x: (severity_order.get(x["severity"], 99), -len(x["raised_by"]))
    )
    
    # Build summary
    model_summaries = [f"**{r.model_name}** ({r.score:.1%}): {r.summary}" for r in valid_reviews]
    if error_reviews:
        model_summaries.append(f"⚠️ Errors: {', '.join(r.model_name for r in error_reviews)}")
    
    summary = f"Council Score: {avg_score:.1%} ({consensus} consensus)\n\n" + "\n\n".join(model_summaries)
    
    return CouncilVerdict(
        score=avg_score,
        verdict=final_verdict,
        consensus=consensus,
        summary=summary,
        individual_reviews=reviews,
        key_issues=key_issues[:10],  # Top 10 issues
    )
