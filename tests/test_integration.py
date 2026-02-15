"""Integration tests for the full pipeline."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from council.core.runner import run_council
from council.core.voting import aggregate_results
from council.core.models import ModelResponse
from council.tasks import get_task


class TestFullPipeline:
    
    @pytest.mark.asyncio
    async def test_pr_review_pipeline(self):
        task = get_task("pr-review")
        
        mock_input = {
            "title": "Add feature",
            "body": "This adds a new feature",
            "author": "testuser",
            "base": "main",
            "head": "feature-branch",
            "diff": "+def hello():\n+    return 'world'",
            "url": "https://github.com/test/repo/pull/1",
        }
        
        mock_response = ModelResponse(
            model_name="mock",
            content='{"score": 0.85, "verdict": "APPROVE", "summary": "Looks good", "issues": [], "positives": ["Clean code"]}',
        )
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["mock"])
        
        assert len(results) == 1
        assert results[0].score == 0.85
        assert results[0].decision == "APPROVE"

    @pytest.mark.asyncio
    async def test_architecture_pipeline(self):
        task = get_task("architecture")
        
        mock_input = {
            "content": "graph TD\n  A-->B-->C",
            "source": "test.mermaid",
            "type": "mermaid",
        }
        
        mock_response = ModelResponse(
            model_name="mock",
            content='{"score": 0.9, "verdict": "APPROVE", "summary": "Clean design", "issues": [], "strengths": ["Simple"], "recommendations": []}',
        )
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["mock"])
        
        assert len(results) == 1
        assert results[0].score == 0.9

    @pytest.mark.asyncio
    async def test_multi_model_consensus(self):
        task = get_task("pr-review")
        
        mock_input = {
            "title": "Test",
            "body": "",
            "author": "user",
            "base": "main",
            "head": "feature",
            "diff": "+print('test')",
            "url": "https://github.com/test/repo/pull/1",
        }
        
        responses = [
            ModelResponse("claude", '{"score": 0.9, "verdict": "APPROVE", "summary": "Good", "issues": []}'),
            ModelResponse("gemini", '{"score": 0.8, "verdict": "APPROVE", "summary": "Nice", "issues": []}'),
            ModelResponse("openai", '{"score": 0.85, "verdict": "APPROVE", "summary": "LGTM", "issues": []}'),
        ]
        
        call_count = 0
        
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = mock_generate
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["claude", "gemini", "openai"])
            verdict = aggregate_results(results)
        
        assert verdict.decision == "APPROVE"
        assert verdict.consensus == "full"
        assert 0.8 <= verdict.score <= 0.9

    @pytest.mark.asyncio
    async def test_split_consensus(self):
        task = get_task("pr-review")
        
        mock_input = {
            "title": "Test",
            "body": "",
            "author": "user",
            "base": "main",
            "head": "feature",
            "diff": "+code",
            "url": "https://github.com/test/repo/pull/1",
        }
        
        responses = [
            ModelResponse("claude", '{"score": 0.9, "verdict": "APPROVE", "summary": "Good", "issues": []}'),
            ModelResponse("gemini", '{"score": 0.4, "verdict": "REQUEST_CHANGES", "summary": "Problems", "issues": [{"severity": "major", "description": "Bug"}]}'),
        ]
        
        call_count = 0
        
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = mock_generate
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["claude", "gemini"])
            verdict = aggregate_results(results)
        
        assert verdict.decision == "REQUEST_CHANGES"  # Any rejection fails
        assert verdict.consensus == "split"


class TestErrorHandling:
    
    @pytest.mark.asyncio
    async def test_model_error_handled(self):
        task = get_task("pr-review")
        
        mock_input = {
            "title": "Test",
            "body": "",
            "author": "user",
            "base": "main",
            "head": "feature",
            "diff": "+code",
            "url": "https://github.com/test/repo/pull/1",
        }
        
        error_response = ModelResponse.from_error("claude", "API rate limited")
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=error_response)
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["claude"])
        
        assert results[0].error is not None
        
        verdict = aggregate_results(results)
        assert verdict.decision == "ERROR"

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        task = get_task("pr-review")
        
        mock_input = {
            "title": "Test",
            "body": "",
            "author": "user",
            "base": "main",
            "head": "feature",
            "diff": "+code",
            "url": "https://github.com/test/repo/pull/1",
        }
        
        responses = [
            ModelResponse("claude", '{"score": 0.9, "verdict": "APPROVE", "summary": "Good", "issues": []}'),
            ModelResponse.from_error("gemini", "API error"),
        ]
        
        call_count = 0
        
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response
        
        with patch("council.core.runner.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = mock_generate
            mock_factory.return_value = mock_client
            
            results = await run_council(task, mock_input, ["claude", "gemini"])
            verdict = aggregate_results(results)
        
        # Should still work with one successful response
        assert verdict.decision == "APPROVE"
        assert verdict.score == 0.9