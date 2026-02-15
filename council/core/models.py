"""Model clients for Claude, Gemini, Mistral, OpenAI, DeepSeek, Groq, and Ollama."""

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
        pass


class ClaudeClient(ModelClient):
    name = "claude"

    def __init__(self):
        import anthropic
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.get_model_version("claude")

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return ModelResponse(model_name=self.name, content=response.content[0].text)
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class GeminiClient(ModelClient):
    name = "gemini"

    def __init__(self):
        from google import genai
        settings = get_settings()
        self.client = genai.Client(api_key=settings.google_api_key)
        self.model = settings.get_model_version("gemini")

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=full_prompt,
            )
            return ModelResponse(model_name=self.name, content=response.text)
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class MistralClient(ModelClient):
    name = "mistral"

    def __init__(self):
        from mistralai import Mistral
        settings = get_settings()
        self.client = Mistral(api_key=settings.mistral_api_key)
        self.model = settings.get_model_version("mistral")

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            response = await self.client.chat.complete_async(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return ModelResponse(model_name=self.name, content=response.choices[0].message.content)
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class OpenAIClient(ModelClient):
    name = "openai"

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.get_model_version("openai")

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
            return ModelResponse(model_name=self.name, content=response.choices[0].message.content)
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class DeepSeekClient(ModelClient):
    name = "deepseek"

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
        )
        self.model = settings.get_model_version("deepseek")

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
            return ModelResponse(model_name=self.name, content=response.choices[0].message.content)
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class GroqClient(ModelClient):
    name = "groq"

    def __init__(self):
        from groq import AsyncGroq
        settings = get_settings()
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.get_model_version("groq")

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
            return ModelResponse(model_name=self.name, content=response.choices[0].message.content)
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class OllamaClient(ModelClient):
    name = "ollama"

    def __init__(self):
        import ollama
        settings = get_settings()
        self.client = ollama.AsyncClient(host=settings.ollama_host)
        self.model = settings.get_model_version("ollama")

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
            return ModelResponse(model_name=f"ollama/{self.model}", content=response["message"]["content"])
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


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
    if name not in CLIENTS:
        raise ValueError(f"Unknown model: {name}. Available: {', '.join(CLIENTS.keys())}")
    return CLIENTS[name]()


def list_available_models() -> list[str]:
    return list(CLIENTS.keys())
