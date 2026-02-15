"""Model clients for Claude, Gemini, Mistral, OpenAI, DeepSeek, and Groq."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from council.config import get_settings


@dataclass
class ModelResponse:
    """Response from a model."""
    
    model_name: str
    content: str
    error: str | None = None

    @classmethod
    def from_error(cls, model_name: str, error: str) -> "ModelResponse":
        return cls(model_name=model_name, content="", error=error)


class ModelClient(ABC):
    """Abstract base class for model clients."""

    name: str = "base"

    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        """Generate a response from the model."""
        pass


# =============================================================================
# Claude (Anthropic)
# =============================================================================

class ClaudeClient(ModelClient):
    """Anthropic Claude client."""

    name = "claude"

    def __init__(self):
        import anthropic
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return ModelResponse(
                model_name=self.name,
                content=response.content[0].text,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# Gemini (Google)
# =============================================================================

class GeminiClient(ModelClient):
    """Google Gemini client."""

    name = "gemini"

    def __init__(self):
        from google import genai
        settings = get_settings()
        self.client = genai.Client(api_key=settings.google_api_key)
        self.model = settings.gemini_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=full_prompt,
            )
            return ModelResponse(
                model_name=self.name,
                content=response.text,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# Mistral
# =============================================================================

class MistralClient(ModelClient):
    """Mistral AI client."""

    name = "mistral"

    def __init__(self):
        from mistralai import Mistral
        settings = get_settings()
        self.client = Mistral(api_key=settings.mistral_api_key)
        self.model = settings.mistral_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return ModelResponse(
                model_name=self.name,
                content=response.choices[0].message.content,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# OpenAI (GPT-4o)
# =============================================================================

class OpenAIClient(ModelClient):
    """OpenAI GPT client."""

    name = "openai"

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
            )
            return ModelResponse(
                model_name=self.name,
                content=response.choices[0].message.content,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# DeepSeek
# =============================================================================

class DeepSeekClient(ModelClient):
    """DeepSeek client (OpenAI-compatible API)."""

    name = "deepseek"

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
        )
        self.model = settings.deepseek_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
            )
            return ModelResponse(
                model_name=self.name,
                content=response.choices[0].message.content,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# Groq (Llama, fast inference)
# =============================================================================

class GroqClient(ModelClient):
    """Groq client for fast Llama inference."""

    name = "groq"

    def __init__(self):
        from groq import AsyncGroq
        settings = get_settings()
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.groq_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=4096,
            )
            return ModelResponse(
                model_name=self.name,
                content=response.choices[0].message.content,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# Ollama (Local)
# =============================================================================

class OllamaClient(ModelClient):
    """Local Ollama client."""

    name = "ollama"

    def __init__(self):
        import ollama
        settings = get_settings()
        self.client = ollama.AsyncClient(host=settings.ollama_host)
        self.model = settings.ollama_model

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={"temperature": 0.3, "num_predict": 4096},
            )
            return ModelResponse(
                model_name=f"ollama/{self.model}",
                content=response["message"]["content"],
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


# =============================================================================
# Factory
# =============================================================================

CLIENTS = {
    "claude": ClaudeClient,
    "gemini": GeminiClient,
    "mistral": MistralClient,
    "openai": OpenAIClient,
    "deepseek": DeepSeekClient,
    "groq": GroqClient,
    "ollama": OllamaClient,
}


def get_model_client(name: str) -> ModelClient:
    """Factory function to get a model client by name."""
    if name not in CLIENTS:
        available = ", ".join(CLIENTS.keys())
        raise ValueError(f"Unknown model: {name}. Available: {available}")
    return CLIENTS[name]()


def list_available_models() -> list[str]:
    """List all available model names."""
    return list(CLIENTS.keys())
