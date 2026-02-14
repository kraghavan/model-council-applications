"""Configuration management for PR Council."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    github_token: str = Field(..., description="GitHub token is required")

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Models
    claude_model: str = "claude-sonnet-4-20250514"
    gemini_model: str = "gemini-1.5-pro"

    # Council configuration
    council_models: str = "claude,gemini"  # Comma-separated list
    approval_threshold: float = 0.7

    @property
    def enabled_models(self) -> list[str]:
        """Parse enabled models from config."""
        return [m.strip().lower() for m in self.council_models.split(",")]

    def validate_api_keys(self) -> list[str]:
        """Check which models have valid API keys configured."""
        available = []
        if "claude" in self.enabled_models and self.anthropic_api_key:
            available.append("claude")
        if "gemini" in self.enabled_models and self.google_api_key:
            available.append("gemini")
        if "ollama" in self.enabled_models:
            # Ollama doesn't need an API key, just assumes it's running
            available.append("ollama")
        return available


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
