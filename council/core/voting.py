"""Voting and consensus logic for aggregating model results."""

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from council.tasks.base import TaskResult


@dataclass
class Verdict:
    """Final aggregated verdict from the council."""

    score: float
    decision: str
    consensus: str  # full, partial, split, none
    summary: str
    results: list["TaskResult"]
    issues: list[dict] = field(default_factory=list)

    @property
    def emoji(self) -> str:
        """Get verdict emoji."""
        return {
            "APPROVE": "✅",
            "REQUEST_CHANGES": "🔴",
            "COMMENT": "💬",
            "REJECT": "❌",
            "ERROR": "⚠️",
        }.get(self.decision, "❓")


def calculate_consensus(decisions: list[str]) -> str:
    """Determine consensus level from decisions."""
    if not decisions:
        return "none"
    
    unique = set(decisions)
    if len(unique) == 1:
        return "full"
    
    counts = Counter(decisions)
    most_common_count = counts.most_common(1)[0][1]
    
    if most_common_count > len(decisions) / 2:
        return "partial"
    
    return "split"


def aggregate_results(
    results: list["TaskResult"],
    threshold: float = 0.7,
    fail_on_any_reject: bool = True,
) -> Verdict:
    """Aggregate multiple task results into a single verdict.
    
    Args:
        results: List of TaskResult from each model
        threshold: Score threshold for approval (0.0-1.0)
        fail_on_any_reject: If True, any REJECT/REQUEST_CHANGES fails the whole verdict
    """
    # Separate valid and error results
    valid = [r for r in results if r.error is None]
    errors = [r for r in results if r.error is not None]
    
    if not valid:
        return Verdict(
            score=0.0,
            decision="ERROR",
            consensus="none",
            summary="All models encountered errors",
            results=results,
        )
    
    # Calculate average score
    avg_score = sum(r.score for r in valid) / len(valid)
    
    # Collect decisions
    decisions = [r.decision for r in valid]
    consensus = calculate_consensus(decisions)
    
    # Determine final decision
    if fail_on_any_reject:
        rejections = {"REJECT", "REQUEST_CHANGES"}
        if any(d in rejections for d in decisions):
            final_decision = "REQUEST_CHANGES"
        elif avg_score >= threshold:
            final_decision = "APPROVE"
        else:
            final_decision = "COMMENT"
    else:
        # Majority vote
        final_decision = Counter(decisions).most_common(1)[0][0]
    
    # Aggregate issues (dedupe by description similarity)
    all_issues = []
    seen_descriptions = set()
    for r in valid:
        for issue in r.issues:
            desc_key = issue.get("description", "")[:50].lower()
            if desc_key not in seen_descriptions:
                seen_descriptions.add(desc_key)
                issue["raised_by"] = [r.model_name]
                all_issues.append(issue)
            else:
                # Find existing and add model name
                for existing in all_issues:
                    if existing.get("description", "")[:50].lower() == desc_key:
                        existing.setdefault("raised_by", []).append(r.model_name)
                        break
    
    # Sort issues by severity
    severity_order = {"critical": 0, "major": 1, "minor": 2, "nit": 3}
    all_issues.sort(key=lambda x: severity_order.get(x.get("severity", ""), 99))
    
    # Build summary
    summaries = [f"**{r.model_name}** ({r.score:.0%}): {r.summary[:80]}..." for r in valid]
    if errors:
        summaries.append(f"⚠️ Errors: {', '.join(r.model_name for r in errors)}")
    
    summary = f"Council Score: {avg_score:.0%} ({consensus} consensus)\n\n" + "\n".join(summaries)
    
    return Verdict(
        score=avg_score,
        decision=final_decision,
        consensus=consensus,
        summary=summary,
        results=results,
        issues=all_issues[:10],
    )
