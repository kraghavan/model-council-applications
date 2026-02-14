"""Claude (Anthropic) reviewer implementation."""

import anthropic

from council.config import get_settings
from council.models.base import BaseReviewer, ReviewResult, parse_review_json
from council.prompts import SYSTEM_PROMPT, build_review_prompt


class ClaudeReviewer(BaseReviewer):
    """Reviewer using Anthropic's Claude API."""

    name = "claude"

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    async def review(self, pr_info: dict, diff: str) -> ReviewResult:
        """Review a PR using Claude."""
        try:
            prompt = build_review_prompt(pr_info, diff)
            
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )
            
            response_text = response.content[0].text
            return parse_review_json(self.name, response_text)
            
        except anthropic.APIError as e:
            return ReviewResult.from_error(self.name, f"API error: {e}")
        except Exception as e:
            return ReviewResult.from_error(self.name, str(e))
