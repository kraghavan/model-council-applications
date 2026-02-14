"""Tests for core council components."""

import pytest

from council.core.voting import aggregate_results, calculate_consensus, Verdict
from council.tasks.base import TaskResult


class TestCalculateConsensus:
    """Tests for consensus calculation."""

    def test_full_consensus(self):
        assert calculate_consensus(["APPROVE", "APPROVE", "APPROVE"]) == "full"

    def test_partial_consensus(self):
        assert calculate_consensus(["APPROVE", "APPROVE", "COMMENT"]) == "partial"

    def test_split_consensus(self):
        assert calculate_consensus(["APPROVE", "COMMENT", "REJECT"]) == "split"

    def test_empty_list(self):
        assert calculate_consensus([]) == "none"


class TestAggregateResults:
    """Tests for result aggregation."""

    def test_unanimous_approve(self):
        results = [
            TaskResult("claude", 0.9, "APPROVE", "Good", []),
            TaskResult("gemini", 0.85, "APPROVE", "Nice", []),
        ]
        verdict = aggregate_results(results)
        assert verdict.decision == "APPROVE"
        assert verdict.consensus == "full"
        assert verdict.score == pytest.approx(0.875)

    def test_any_reject_fails(self):
        results = [
            TaskResult("claude", 0.9, "APPROVE", "Good", []),
            TaskResult("gemini", 0.4, "REQUEST_CHANGES", "Problems", []),
        ]
        verdict = aggregate_results(results, fail_on_any_reject=True)
        assert verdict.decision == "REQUEST_CHANGES"

    def test_below_threshold(self):
        results = [
            TaskResult("claude", 0.5, "COMMENT", "Meh", []),
            TaskResult("gemini", 0.6, "COMMENT", "Okay", []),
        ]
        verdict = aggregate_results(results, threshold=0.7)
        assert verdict.decision == "COMMENT"

    def test_all_errors(self):
        results = [
            TaskResult.from_error("claude", "API failed"),
            TaskResult.from_error("gemini", "Timeout"),
        ]
        verdict = aggregate_results(results)
        assert verdict.decision == "ERROR"
        assert verdict.consensus == "none"

    def test_partial_errors(self):
        results = [
            TaskResult("claude", 0.8, "APPROVE", "Good", []),
            TaskResult.from_error("gemini", "Failed"),
        ]
        verdict = aggregate_results(results)
        assert verdict.decision == "APPROVE"
        assert verdict.score == pytest.approx(0.8)

    def test_issue_aggregation(self):
        results = [
            TaskResult("claude", 0.6, "COMMENT", "Issues", [
                {"severity": "major", "description": "Bug in auth"},
                {"severity": "minor", "description": "Style issue"},
            ]),
            TaskResult("gemini", 0.5, "COMMENT", "Problems", [
                {"severity": "major", "description": "Bug in auth"},  # Duplicate
            ]),
        ]
        verdict = aggregate_results(results)
        # Should dedupe the auth bug
        assert len(verdict.issues) == 2


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_from_error(self):
        result = TaskResult.from_error("test", "Something failed")
        assert result.model_name == "test"
        assert result.score == 0.0
        assert result.decision == "ERROR"
        assert result.error == "Something failed"

    def test_normal_result(self):
        result = TaskResult(
            model_name="claude",
            score=0.85,
            decision="APPROVE",
            summary="All good",
            issues=[],
        )
        assert result.error is None
        assert result.score == 0.85


class TestVerdict:
    """Tests for Verdict dataclass."""

    def test_emoji_approve(self):
        verdict = Verdict(0.9, "APPROVE", "full", "Good", [])
        assert verdict.emoji == "✅"

    def test_emoji_reject(self):
        verdict = Verdict(0.3, "REQUEST_CHANGES", "full", "Bad", [])
        assert verdict.emoji == "🔴"

    def test_emoji_error(self):
        verdict = Verdict(0.0, "ERROR", "none", "Failed", [])
        assert verdict.emoji == "⚠️"
