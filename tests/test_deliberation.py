"""Tests for multi-round deliberation."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from council.core.deliberation import (
    Deliberation,
    DeliberationConfig,
    DeliberationResult,
    run_deliberation,
)
from council.core.models import ModelResponse
from council.tasks import get_task
from council.db.schema import init_db


class TestDeliberationConfig:
    """Tests for DeliberationConfig."""

    def test_default_config(self):
        config = DeliberationConfig()
        
        assert config.rounds == 2
        assert config.max_rounds == 5
        assert config.storage_enabled is True
        assert config.early_stop_on_consensus is True

    def test_custom_config(self):
        config = DeliberationConfig(
            rounds=3,
            max_rounds=10,
            storage_enabled=False,
            early_stop_on_consensus=False,
        )
        
        assert config.rounds == 3
        assert config.max_rounds == 10
        assert config.storage_enabled is False


class TestDeliberation:
    """Tests for Deliberation class."""

    @pytest.fixture
    def task(self):
        return get_task("pr-review")

    @pytest.fixture
    def mock_input(self):
        return {
            "title": "Test PR",
            "body": "Description",
            "author": "testuser",
            "base": "main",
            "head": "feature",
            "diff": "+def test():\n+    pass",
            "url": "https://github.com/owner/repo/pull/1",
        }

    @pytest.mark.asyncio
    async def test_single_round(self, task, mock_input):
        """Test single round deliberation (no multi-round)."""
        config = DeliberationConfig(rounds=1, storage_enabled=False)
        deliberation = Deliberation(task, ["mock"], config)
        
        mock_response = ModelResponse(
            "mock",
            '{"score": 0.85, "verdict": "APPROVE", "summary": "Good", "issues": []}'
        )
        
        with patch("council.core.deliberation.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_client
            
            result = await deliberation.run(mock_input)
        
        assert result.total_rounds == 1
        assert result.verdict.decision == "APPROVE"
        assert result.verdict.score == 0.85
        assert len(result.opinion_changes) == 0

    @pytest.mark.asyncio
    async def test_multi_round_opinion_change(self, task, mock_input):
        """Test that opinions can change between rounds."""
        config = DeliberationConfig(rounds=2, storage_enabled=False, early_stop_on_consensus=False)
        deliberation = Deliberation(task, ["mock"], config)
        
        # Round 1: COMMENT
        # Round 2: APPROVE (changed mind)
        responses = [
            ModelResponse("mock", '{"score": 0.6, "verdict": "COMMENT", "summary": "Needs work", "issues": [{"severity": "major", "description": "Missing tests"}]}'),
            ModelResponse("mock", '{"score": 0.85, "verdict": "APPROVE", "summary": "Reconsidered, looks good", "issues": []}'),
        ]
        call_count = 0
        
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response
        
        with patch("council.core.deliberation.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = mock_generate
            mock_factory.return_value = mock_client
            
            result = await deliberation.run(mock_input)
        
        assert result.total_rounds == 2
        assert result.verdict.decision == "APPROVE"
        assert len(result.opinion_changes) == 1
        assert result.opinion_changes[0]["verdict_before"] == "COMMENT"
        assert result.opinion_changes[0]["verdict_after"] == "APPROVE"

    @pytest.mark.asyncio
    async def test_early_stop_on_consensus(self, task, mock_input):
        """Test that deliberation stops early if all models agree."""
        config = DeliberationConfig(
            rounds=5,
            storage_enabled=False,
            early_stop_on_consensus=True,
        )
        deliberation = Deliberation(task, ["model1", "model2"], config)
        
        # Both models agree from round 1
        mock_response = ModelResponse(
            "mock",
            '{"score": 0.9, "verdict": "APPROVE", "summary": "Perfect", "issues": []}'
        )
        
        with patch("council.core.deliberation.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_client
            
            result = await deliberation.run(mock_input)
        
        # Should stop after round 1 (consensus reached)
        assert result.total_rounds == 1

    @pytest.mark.asyncio
    async def test_continues_without_consensus(self, task, mock_input):
        """Test that deliberation continues if no consensus."""
        config = DeliberationConfig(
            rounds=2,
            storage_enabled=False,
            early_stop_on_consensus=True,
        )
        deliberation = Deliberation(task, ["model1", "model2"], config)
        
        # Models disagree
        responses = [
            # Round 1
            ModelResponse("model1", '{"score": 0.9, "verdict": "APPROVE", "summary": "Good", "issues": []}'),
            ModelResponse("model2", '{"score": 0.5, "verdict": "REQUEST_CHANGES", "summary": "Bad", "issues": []}'),
            # Round 2
            ModelResponse("model1", '{"score": 0.85, "verdict": "APPROVE", "summary": "Still good", "issues": []}'),
            ModelResponse("model2", '{"score": 0.6, "verdict": "COMMENT", "summary": "Better", "issues": []}'),
        ]
        call_count = 0
        
        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            response = responses[call_count % len(responses)]
            call_count += 1
            return response
        
        with patch("council.core.deliberation.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = mock_generate
            mock_factory.return_value = mock_client
            
            result = await deliberation.run(mock_input)
        
        # Should complete all rounds (no consensus)
        assert result.total_rounds == 2

    @pytest.mark.asyncio
    async def test_with_storage(self, task, mock_input, tmp_path):
        """Test deliberation with storage enabled."""
        db_path = tmp_path / "test.db"
        init_db(str(db_path))
        
        config = DeliberationConfig(rounds=1, storage_enabled=True)
        
        from council.db.storage import CouncilStorage
        storage = CouncilStorage(str(db_path))
        
        deliberation = Deliberation(task, ["mock"], config, storage=storage)
        
        mock_response = ModelResponse(
            "mock",
            '{"score": 0.8, "verdict": "APPROVE", "summary": "Good", "issues": []}'
        )
        
        with patch("council.core.deliberation.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_client
            
            result = await deliberation.run(mock_input)
        
        # Check that data was persisted
        assert result.session_id != "no-storage"
        
        sessions = storage.get_recent_sessions()
        assert len(sessions) == 1
        assert sessions[0]["final_verdict"] == "APPROVE"

    def test_format_opinions_for_context(self, task):
        """Test formatting of opinions for injection."""
        from council.tasks.base import TaskResult
        
        deliberation = Deliberation(task, ["claude", "gemini"])
        
        opinions = [
            TaskResult("claude", 0.8, "APPROVE", "Looks good", []),
            TaskResult("gemini", 0.6, "COMMENT", "Needs review", [
                {"severity": "major", "description": "Missing validation"}
            ]),
        ]
        
        context = deliberation._format_opinions_for_context(opinions)
        
        assert "claude" in context
        assert "gemini" in context
        assert "80%" in context
        assert "APPROVE" in context
        assert "Missing validation" in context

    def test_inject_opinions_context(self, task):
        """Test injecting opinions into prompt."""
        deliberation = Deliberation(task, ["claude"])
        
        original_prompt = "Review this code..."
        opinions_context = "## Previous opinions..."
        
        injected = deliberation._inject_opinions_context(
            original_prompt, opinions_context, round_number=2
        )
        
        assert original_prompt in injected
        assert opinions_context in injected
        assert "Round 2" in injected

    def test_detect_opinion_changes_score_change(self, task):
        """Test detection of score changes."""
        from council.tasks.base import TaskResult
        
        deliberation = Deliberation(
            task, ["claude"],
            config=DeliberationConfig(storage_enabled=False)
        )
        
        prev = [TaskResult("claude", 0.6, "COMMENT", "Okay", [])]
        curr = [TaskResult("claude", 0.85, "APPROVE", "Good", [])]
        
        changes = deliberation._detect_opinion_changes(
            "session-1", prev, curr, 1, 2
        )
        
        assert len(changes) == 1
        assert changes[0]["model"] == "claude"
        assert changes[0]["score_before"] == 0.6
        assert changes[0]["score_after"] == 0.85

    def test_detect_opinion_changes_no_change(self, task):
        """Test no change detection when opinions stay same."""
        from council.tasks.base import TaskResult
        
        deliberation = Deliberation(
            task, ["claude"],
            config=DeliberationConfig(storage_enabled=False)
        )
        
        prev = [TaskResult("claude", 0.85, "APPROVE", "Good", [])]
        curr = [TaskResult("claude", 0.86, "APPROVE", "Still good", [])]  # Minor score change
        
        changes = deliberation._detect_opinion_changes(
            "session-1", prev, curr, 1, 2
        )
        
        # Score change is < 0.05, so no change recorded
        assert len(changes) == 0


class TestRunDeliberation:
    """Tests for run_deliberation convenience function."""

    @pytest.mark.asyncio
    async def test_run_deliberation(self):
        task = get_task("pr-review")
        
        mock_input = {
            "title": "Test",
            "body": "",
            "author": "user",
            "base": "main",
            "head": "feature",
            "diff": "+code",
            "url": "https://github.com/owner/repo/pull/1",
        }
        
        mock_response = ModelResponse(
            "mock",
            '{"score": 0.8, "verdict": "APPROVE", "summary": "OK", "issues": []}'
        )
        
        with patch("council.core.deliberation.get_model_client") as mock_factory:
            mock_client = MagicMock()
            mock_client.generate = AsyncMock(return_value=mock_response)
            mock_factory.return_value = mock_client
            
            result = await run_deliberation(
                task=task,
                input_data=mock_input,
                models=["mock"],
                rounds=1,
                storage_enabled=False,
            )
        
        assert isinstance(result, DeliberationResult)
        assert result.verdict.decision == "APPROVE"
