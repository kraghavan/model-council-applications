"""Configuration management for Model Council.

Configuration priority:
1. Environment variables (.env)
2. council.yaml (project or global)
3. Hardcoded defaults
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_config_file() -> Optional[Path]:
    """Find council.yaml config file.
    
    Search order:
    1. ./council.yaml (current directory)
    2. ./council.yml
    3. ~/.council/council.yaml (user global)
    4. ~/.config/council/council.yaml
    """
    search_paths = [
        Path("council.yaml"),
        Path("council.yml"),
        Path.home() / ".council" / "council.yaml",
        Path.home() / ".config" / "council" / "council.yaml",
    ]
    
    for path in search_paths:
        if path.exists():
            return path
    
    return None


def load_yaml_config() -> dict[str, Any]:
    """Load configuration from council.yaml."""
    config_path = find_config_file()
    
    if config_path:
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    
    return {}


# Default configuration
DEFAULT_CONFIG = {
    "models": {
        "claude": {"version": "claude-sonnet-4-20250514"},
        "openai": {"version": "gpt-4o"},
        "gemini": {"version": "gemini-2.0-flash"},
        "mistral": {"version": "mistral-large-latest"},
        "deepseek": {"version": "deepseek-chat"},
        "groq": {"version": "llama-3.3-70b-versatile"},
        "ollama": {"version": "llama3.2", "host": "http://localhost:11434"},
    },
    "storage": {
        "enabled": True,
        "path": "~/.council/data/council.db",
    },
    "deliberation": {
        "enabled": True,
        "rounds": 2,
        "max_rounds": 5,
        "early_stop_on_consensus": True,
    },
    "review": {
        "approval_threshold": 0.7,
    },
    "cache": {
        "context_ttl_seconds": 3600,  # 1 hour default
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Settings(BaseSettings):
    """Application settings. Priority: ENV > council.yaml > defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys (from .env only)
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    github_token: Optional[str] = None

    # Storage settings (can override via ENV)
    council_storage_enabled: Optional[bool] = None
    council_storage_path: Optional[str] = None

    # Deliberation settings (can override via ENV)
    council_deliberation_enabled: Optional[bool] = None
    council_deliberation_rounds: Optional[int] = None

    # Model selection (can override via ENV)
    council_models: Optional[str] = None  # Comma-separated
    
    # Individual model versions (can override via ENV)
    claude_model: Optional[str] = None
    openai_model: Optional[str] = None
    gemini_model: Optional[str] = None
    mistral_model: Optional[str] = None
    deepseek_model: Optional[str] = None
    groq_model: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_host: Optional[str] = None

    # Review settings
    approval_threshold: Optional[float] = None

    # Cache settings (can override via ENV)
    council_context_cache_ttl: Optional[int] = None  # Seconds

    # Internal: loaded config
    _yaml_config: dict = {}
    _merged_config: dict = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        yaml_config = load_yaml_config()
        object.__setattr__(self, '_yaml_config', yaml_config)
        object.__setattr__(self, '_merged_config', deep_merge(DEFAULT_CONFIG, yaml_config))

    def _get_config(self, *keys: str, default: Any = None) -> Any:
        """Get nested config value."""
        value = self._merged_config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    # =========================================================================
    # Model Configuration
    # =========================================================================
    
    def get_model_version(self, model_name: str) -> str:
        """Get model version. Priority: ENV > yaml > default."""
        # Check ENV first
        env_attr = f"{model_name}_model"
        env_value = getattr(self, env_attr, None)
        if env_value:
            return env_value
        
        # Check merged config
        return self._get_config("models", model_name, "version", default="")

    def get_ollama_host(self) -> str:
        """Get Ollama host."""
        if self.ollama_host:
            return self.ollama_host
        return self._get_config("models", "ollama", "host", default="http://localhost:11434")

    @property
    def enabled_models(self) -> list[str]:
        """Get list of enabled models."""
        if self.council_models:
            return [m.strip().lower() for m in self.council_models.split(",")]
        
        default_models = self._get_config("models", "default")
        if default_models:
            return default_models
        
        return ["claude", "gemini"]

    def get_available_models(self) -> list[str]:
        """Get models that are both enabled and have valid credentials."""
        available = []
        model_keys = {
            "claude": self.anthropic_api_key,
            "gemini": self.google_api_key,
            "mistral": self.mistral_api_key,
            "openai": self.openai_api_key,
            "deepseek": self.deepseek_api_key,
            "groq": self.groq_api_key,
            "ollama": True,  # No key needed
        }
        for model in self.enabled_models:
            if model in model_keys and model_keys[model]:
                available.append(model)
        return available

    # =========================================================================
    # Storage Configuration
    # =========================================================================
    
    @property
    def storage_enabled(self) -> bool:
        """Check if storage is enabled."""
        if self.council_storage_enabled is not None:
            return self.council_storage_enabled
        return self._get_config("storage", "enabled", default=True)

    @property
    def storage_path(self) -> str:
        """Get storage path."""
        if self.council_storage_path:
            return self.council_storage_path
        path = self._get_config("storage", "path", default="~/.council/data/council.db")
        return str(Path(path).expanduser())

    # =========================================================================
    # Deliberation Configuration
    # =========================================================================
    
    @property
    def deliberation_enabled(self) -> bool:
        """Check if deliberation (multi-round) is enabled."""
        if self.council_deliberation_enabled is not None:
            return self.council_deliberation_enabled
        return self._get_config("deliberation", "enabled", default=True)

    @property
    def deliberation_rounds(self) -> int:
        """Get number of deliberation rounds."""
        if self.council_deliberation_rounds is not None:
            return self.council_deliberation_rounds
        return self._get_config("deliberation", "rounds", default=2)

    @property
    def deliberation_max_rounds(self) -> int:
        """Get maximum deliberation rounds allowed."""
        return self._get_config("deliberation", "max_rounds", default=5)

    @property
    def early_stop_on_consensus(self) -> bool:
        """Check if early stop on consensus is enabled."""
        return self._get_config("deliberation", "early_stop_on_consensus", default=True)

    # =========================================================================
    # Review Configuration
    # =========================================================================
    
    @property
    def threshold(self) -> float:
        """Get approval threshold."""
        if self.approval_threshold is not None:
            return self.approval_threshold
        return self._get_config("review", "approval_threshold", default=0.7)

    # =========================================================================
    # Cache Configuration
    # =========================================================================
    
    @property
    def context_cache_ttl(self) -> int:
        """Get context cache TTL in seconds."""
        if self.council_context_cache_ttl is not None:
            return self.council_context_cache_ttl
        return self._get_config("cache", "context_ttl_seconds", default=3600)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache (useful for testing)."""
    get_settings.cache_clear()
