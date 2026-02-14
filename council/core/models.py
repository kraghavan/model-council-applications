"""Model clients for Claude, Gemini, and Ollama."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import anthropic
import google.generativeai as genai
import ollama
from mistralai import Mistral

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


class ClaudeClient(ModelClient):
    """Anthropic Claude client."""

    name = "claude"

    def __init__(self):
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
        except anthropic.APIError as e:
            return ModelResponse.from_error(self.name, f"API error: {e}")
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class GeminiClient(ModelClient):
    """Google Gemini client."""

    name = "gemini"

    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.google_api_key)
        self.model = genai.GenerativeModel(
            model_name=settings.gemini_model,
        )

    async def generate(self, system_prompt: str, user_prompt: str) -> ModelResponse:
        try:
            # Gemini combines system + user in the prompt
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            response = await self.model.generate_content_async(
                full_prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=4096,
                    temperature=0.3,
                ),
            )
            return ModelResponse(
                model_name=self.name,
                content=response.text,
            )
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class OllamaClient(ModelClient):
    """Local Ollama client."""

    name = "ollama"

    def __init__(self):
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
        except ollama.ResponseError as e:
            return ModelResponse.from_error(self.name, f"Ollama error: {e}")
        except Exception as e:
            return ModelResponse.from_error(self.name, str(e))


class MistralClient(ModelClient):
    name = "mistral"

    def __init__(self):
        settings = get_settings()
        self.client = Mistral(api_key=settings.mistral_api_key)
        self.model = "mistral-large-latest"  # or mixtral-8x22b

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

def get_model_client(name: str) -> ModelClient:
    """Factory function to get a model client by name."""
    clients = {
        "claude": ClaudeClient,
        "gemini": GeminiClient,
        "ollama": OllamaClient,
    }
    if name not in clients:
        raise ValueError(f"Unknown model: {name}. Available: {list(clients.keys())}")
    return clients[name]()
