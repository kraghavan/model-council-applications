"""Gemini (Google) reviewer implementation."""

import google.generativeai as genai

from council.config import get_settings
from council.models.base import BaseReviewer, ReviewResult, parse_review_json
from council.prompts import SYSTEM_PROMPT, build_review_prompt


class GeminiReviewer(BaseReviewer):
    """Reviewer using Google's Gemini API."""

    name = "gemini"

    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.google_api_key)
        self.model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
        )

    async def review(self, pr_info: dict, diff: str) -> ReviewResult:
        """Review a PR using Gemini."""
        try:
            prompt = build_review_prompt(pr_info, diff)
            
            # Gemini's async API
            response = await self.model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=4096,
                    temperature=0.3,
                ),
            )
            
            response_text = response.text
            return parse_review_json(self.name, response_text)
            
        except Exception as e:
            return ReviewResult.from_error(self.name, str(e))
