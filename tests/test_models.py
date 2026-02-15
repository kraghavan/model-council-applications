"""Tests for model clients."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from council.core.models import (
    ModelResponse,
    get_model_client,
    list_available_models,
    CLIENTS,
)


class TestModelResponse:
    
    def test_create_response(self):
        resp = ModelResponse(model_name="test", content="Hello")
        assert resp.model_name == "test"
        assert resp.content == "Hello"
        assert resp.error is None

    def test_from_error(self):
        resp = ModelResponse.from_error("test", "API failed")
        assert resp.model_name == "test"
        assert resp.content == ""
        assert resp.error == "API failed"


class TestModelFactory:
    
    def test_list_available_models(self):
        models = list_available_models()
        assert "claude" in models
        assert "gemini" in models
        assert "openai" in models
        assert "deepseek" in models
        assert "groq" in models
        assert "ollama" in models

    def test_get_unknown_model(self):
        with pytest.raises(ValueError, match="Unknown model"):
            get_model_client("nonexistent")

    def test_all_clients_registered(self):
        expected = ["claude", "gemini", "mistral", "openai", "deepseek", "groq", "ollama"]
        for model in expected:
            assert model in CLIENTS


class TestClaudeClient:
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        with patch("council.core.models.get_settings") as mock_settings:
            mock_settings.return_value.anthropic_api_key = "test-key"
            mock_settings.return_value.claude_model = "claude-test"
            
            with patch("anthropic.AsyncAnthropic") as mock_anthropic:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Test response")]
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_anthropic.return_value = mock_client
                
                from council.core.models import ClaudeClient
                client = ClaudeClient()
                result = await client.generate("system", "user")
                
                assert result.content == "Test response"
                assert result.error is None


class TestOpenAIClient:
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        with patch("council.core.models.get_settings") as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.openai_model = "gpt-4o"
            
            with patch("openai.AsyncOpenAI") as mock_openai:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="GPT response"))]
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                mock_openai.return_value = mock_client
                
                from council.core.models import OpenAIClient
                client = OpenAIClient()
                result = await client.generate("system", "user")
                
                assert result.content == "GPT response"
                assert result.error is None


class TestDeepSeekClient:
    
    @pytest.mark.asyncio
    async def test_uses_correct_base_url(self):
        with patch("council.core.models.get_settings") as mock_settings:
            mock_settings.return_value.deepseek_api_key = "test-key"
            mock_settings.return_value.deepseek_model = "deepseek-chat"
            
            with patch("openai.AsyncOpenAI") as mock_openai:
                from council.core.models import DeepSeekClient
                client = DeepSeekClient()
                
                # Verify base_url was passed
                mock_openai.assert_called_once()
                call_kwargs = mock_openai.call_args[1]
                assert call_kwargs["base_url"] == "https://api.deepseek.com/v1"