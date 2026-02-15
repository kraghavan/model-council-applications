"""Tests for core council components."""

import pytest

from council.core.voting import aggregate_results, calculate_consensus, Verdict
from council.tasks.base import TaskResult
from council.core.runner import run_council

class TestRunner:
    
    @pytest.mark.asyncio
    async def test_run_council_parallel(self):
        """Verify models run in parallel."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from council.tasks import get_task
        from council.core.models import ModelResponse
        
        task = get_task("pr-review")
        mock_input = {
            "title": "Test", "body": "", "author": "user",
            "base": "main", "head": "feature", "diff": "+code",
            "url": "https://github.com/test/repo/pull/1",
        }
        
        call_times = []
        
        async def mock_generate(*args, **kwargs):
            import asyncio
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)  # Simulate API latency
            return ModelResponse("mock", '{"score": 0.8, "verdict": "APPROVE", "summary": "OK", "issues": []}')
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = mock_generate
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["m1", "m2", "m3"])
        
        assert len(results) == 3
        # All should start at roughly the same time (parallel)
        if len(call_times) >= 2:
            assert call_times[-1] - call_times[0] < 0.05  # Started within 50ms


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
