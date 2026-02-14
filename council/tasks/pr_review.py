"""Pull Request review task implementation."""

import re

import httpx

from council.config import get_settings
from council.tasks.base import BaseTask, TaskResult


class PRReviewTask(BaseTask):
    """Review GitHub pull requests with multiple models."""

    name = "pr-review"
    description = "Review GitHub pull requests for code quality, bugs, and best practices"

    async def fetch_input(self, source: str) -> dict:
        """Fetch PR data from GitHub.
        
        Args:
            source: PR URL (full URL or owner/repo#number format)
        """
        owner, repo, number = self._parse_pr_url(source)
        settings = get_settings()
        
        if not settings.github_token:
            raise ValueError("GITHUB_TOKEN is required for PR review")
        
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        
        async with httpx.AsyncClient() as client:
            # Fetch PR metadata
            pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
            pr_response = await client.get(pr_url, headers=headers)
            pr_response.raise_for_status()
            pr_data = pr_response.json()
            
            # Fetch diff
            diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_response = await client.get(pr_url, headers=diff_headers)
            diff_response.raise_for_status()
            diff = diff_response.text
            
            # Truncate large diffs
            max_chars = 50000
            if len(diff) > max_chars:
                diff = diff[:max_chars] + "\n\n... [truncated] ..."
        
        return {
            "owner": owner,
            "repo": repo,
            "number": number,
            "title": pr_data["title"],
            "body": pr_data.get("body") or "",
            "author": pr_data["user"]["login"],
            "base": pr_data["base"]["ref"],
            "head": pr_data["head"]["ref"],
            "url": pr_data["html_url"],
            "diff": diff,
        }

    def _parse_pr_url(self, url: str) -> tuple[str, str, int]:
        """Parse PR URL into (owner, repo, number)."""
        # Full URL: https://github.com/owner/repo/pull/123
        match = re.match(
            r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)",
            url
        )
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        
        # Short: owner/repo#123
        match = re.match(r"([^/]+)/([^#]+)#(\d+)", url)
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        
        # Path: owner/repo/pull/123
        match = re.match(r"([^/]+)/([^/]+)/pull/(\d+)", url)
        if match:
            return match.group(1), match.group(2), int(match.group(3))
        
        raise ValueError(
            f"Invalid PR URL: {url}\n"
            "Expected: https://github.com/owner/repo/pull/123 or owner/repo#123"
        )

    def build_prompt(self, input_data: dict) -> tuple[str, str]:
        """Build PR review prompts."""
        system_prompt = """You are an expert code reviewer participating in a council of AI reviewers.
Your job is to analyze pull requests and provide honest, constructive feedback.

Focus on:
- Code correctness and potential bugs
- Security vulnerabilities  
- Performance concerns
- Code clarity and maintainability
- Test coverage gaps
- API design issues

Be direct and specific. Respond ONLY with valid JSON."""

        user_prompt = f"""Review this pull request and provide your assessment.

## Pull Request
- **Title:** {input_data['title']}
- **Author:** {input_data['author']}
- **Branch:** {input_data['base']} ← {input_data['head']}
- **Description:** {input_data['body'] or 'No description'}

## Diff
```diff
{input_data['diff']}
```

## Instructions
Respond with ONLY valid JSON (no markdown, no explanation):

{{
    "score": <float 0.0-1.0>,
    "verdict": "<APPROVE|REQUEST_CHANGES|COMMENT>",
    "summary": "<one paragraph assessment>",
    "issues": [
        {{
            "severity": "<critical|major|minor|nit>",
            "file": "<filename or null>",
            "line": <line number or null>,
            "description": "<what's wrong and how to fix>"
        }}
    ],
    "positives": ["<good things about this PR>"]
}}

Scoring:
- 0.9-1.0: Excellent, ready to merge
- 0.7-0.9: Good, minor issues only
- 0.5-0.7: Needs work
- 0.3-0.5: Major concerns
- 0.0-0.3: Critical issues"""

        return system_prompt, user_prompt

    def parse_response(self, model_name: str, response: str) -> TaskResult:
        """Parse model response into TaskResult."""
        data = self.parse_json_response(model_name, response)
        
        if data is None:
            return TaskResult.from_error(model_name, "Could not parse JSON response")
        
        # Parse issues
        issues = []
        for issue in data.get("issues", []):
            issues.append({
                "severity": issue.get("severity", "minor"),
                "file": issue.get("file"),
                "line": issue.get("line"),
                "description": issue.get("description", ""),
            })
        
        return TaskResult(
            model_name=model_name,
            score=float(data.get("score", 0.5)),
            decision=data.get("verdict", "COMMENT"),
            summary=data.get("summary", ""),
            issues=issues,
            extras={"positives": data.get("positives", [])},
        )
