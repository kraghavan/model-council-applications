"""GitHub API client for fetching PR information."""

import re
from dataclasses import dataclass

import httpx

from council.config import get_settings


@dataclass
class PullRequest:
    """Represents a GitHub pull request."""

    owner: str
    repo: str
    number: int
    title: str
    body: str
    author: str
    base: str
    head: str
    diff: str
    url: str


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse a GitHub PR URL into owner, repo, and PR number.
    
    Supports formats:
    - https://github.com/owner/repo/pull/123
    - github.com/owner/repo/pull/123
    - owner/repo#123
    - owner/repo/pull/123
    """
    # Full URL format
    match = re.match(
        r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        url
    )
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    
    # Short format: owner/repo#123
    match = re.match(r"([^/]+)/([^#]+)#(\d+)", url)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    
    # Path format: owner/repo/pull/123
    match = re.match(r"([^/]+)/([^/]+)/pull/(\d+)", url)
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    
    raise ValueError(
        f"Invalid PR URL format: {url}\n"
        "Expected: https://github.com/owner/repo/pull/123 or owner/repo#123"
    )


async def fetch_pull_request(pr_url: str) -> PullRequest:
    """Fetch PR information and diff from GitHub."""
    settings = get_settings()
    owner, repo, number = parse_pr_url(pr_url)
    
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    async with httpx.AsyncClient() as client:
        # Fetch PR metadata
        pr_response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
            headers=headers,
        )
        pr_response.raise_for_status()
        pr_data = pr_response.json()
        
        # Fetch diff
        diff_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
        diff_response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
            headers=diff_headers,
        )
        diff_response.raise_for_status()
        diff = diff_response.text
        
        # Truncate very large diffs
        max_diff_chars = 50000
        if len(diff) > max_diff_chars:
            diff = diff[:max_diff_chars] + "\n\n... [diff truncated due to size] ..."
    
    return PullRequest(
        owner=owner,
        repo=repo,
        number=number,
        title=pr_data["title"],
        body=pr_data.get("body") or "",
        author=pr_data["user"]["login"],
        base=pr_data["base"]["ref"],
        head=pr_data["head"]["ref"],
        diff=diff,
        url=pr_data["html_url"],
    )
