"""Ollama (local) reviewer implementation."""

import ollama

from council.config import get_settings
from council.models.base import BaseReviewer, ReviewResult, parse_review_json
from council.prompts import SYSTEM_PROMPT, build_review_prompt


class OllamaReviewer(BaseReviewer):
    """Reviewer using local Ollama models."""

    name = "ollama"

    def __init__(self):
        settings = get_settings()
        self.client = ollama.AsyncClient(host=settings.ollama_host)
        self.model = settings.ollama_model

    async def review(self, pr_info: dict, diff: str) -> ReviewResult:
        """Review a PR using Ollama."""
        try:
            prompt = build_review_prompt(pr_info, diff)
            
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                options={
                    "temperature": 0.3,
                    "num_predict": 4096,
                },
            )
            
            response_text = response["message"]["content"]
            result = parse_review_json(self.name, response_text)
            # Tag with the actual model name
            result.model_name = f"ollama/{self.model}"
            return result
            
        except ollama.ResponseError as e:
            return ReviewResult.from_error(self.name, f"Ollama error: {e}")
        except Exception as e:
            return ReviewResult.from_error(self.name, str(e))
