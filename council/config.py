"""Configuration management for Model Council."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_models_config() -> dict[str, Any]:
    """Load models config from council.yaml."""
    config_paths = [
        Path("council.yaml"),
        Path("council.yml"),
        Path.home() / ".config" / "council" / "council.yaml",
    ]
    
    for path in config_paths:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)
    
    return {
        "models": {
            "claude": {"default": "claude-sonnet-4-20250514"},
            "openai": {"default": "gpt-4o"},
            "gemini": {"default": "gemini-2.0-flash"},
            "mistral": {"default": "mistral-large-latest"},
            "deepseek": {"default": "deepseek-chat"},
            "groq": {"default": "llama-3.3-70b-versatile"},
            "ollama": {"default": "llama3.2"},
        },
        "council": {
            "enabled_models": ["claude", "gemini"],
            "approval_threshold": 0.7,
        },
    }


class Settings(BaseSettings):
    """Application settings. Priority: ENV > council.yaml > defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    mistral_api_key: str | None = None
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    groq_api_key: str | None = None
    github_token: str | None = None

    # Ollama
    ollama_host: str = "http://localhost:11434"

    # Model versions - ENV overrides yaml
    claude_model: str | None = None
    gemini_model: str | None = None
    mistral_model: str | None = None
    openai_model: str | None = None
    deepseek_model: str | None = None
    groq_model: str | None = None
    ollama_model: str | None = None

    # Council settings
    council_models: str | None = None
    approval_threshold: float | None = None

    _yaml_config: dict = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, '_yaml_config', load_models_config())

    def get_model_version(self, model_name: str) -> str:
        """Get model version. Priority: ENV > yaml > default."""
        env_value = getattr(self, f"{model_name}_model", None)
        if env_value:
            return env_value
        
        yaml_models = self._yaml_config.get("models", {})
        if model_name in yaml_models:
            return yaml_models[model_name].get("default", "")
        
        defaults = {
            "claude": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
            "gemini": "gemini-2.0-flash",
            "mistral": "mistral-large-latest",
            "deepseek": "deepseek-chat",
            "groq": "llama-3.3-70b-versatile",
            "ollama": "llama3.2",
        }
        return defaults.get(model_name, "")

    @property
    def enabled_models(self) -> list[str]:
        """Get enabled models. Priority: ENV > yaml."""
        if self.council_models:
            return [m.strip().lower() for m in self.council_models.split(",")]
        yaml_council = self._yaml_config.get("council", {})
        return yaml_council.get("enabled_models", ["claude", "gemini"])

    @property
    def threshold(self) -> float:
        """Get approval threshold."""
        if self.approval_threshold is not None:
            return self.approval_threshold
        yaml_council = self._yaml_config.get("council", {})
        return yaml_council.get("approval_threshold", 0.7)

    def get_available_models(self) -> list[str]:
        """Get models with valid credentials."""
        available = []
        model_keys = {
            "claude": self.anthropic_api_key,
            "gemini": self.google_api_key,
            "mistral": self.mistral_api_key,
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "groq": self.groq_api_key,
            "ollama": True,
        }
        for model in self.enabled_models:
            if model in model_keys and model_keys[model]:
                available.append(model)
        return available


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
